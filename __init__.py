"""Per-project MCP servers: project files become NATIVE mcp__server__tool tools."""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOOLSET = "project-mcp"
STATE_KEY = "projects"
CONNECT_TIMEOUT_S = 8.0

_SCHEMAS: Dict[str, dict] = {}


def _schema(name: str, description: str, properties: dict, required: Optional[list] = None) -> None:
    params = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    _SCHEMAS[name] = {"name": name, "description": description, "parameters": params}


_schema(
    "project_mcp_sync",
    "Load/refresh the current project's MCP servers (.hermes/mcp.json, .mcp.json, "
    ".claude/settings*.json). After sync the servers are NATIVE tools named "
    "mcp__<server>__<tool>; they are callable directly from the next turn "
    "(the current turn's tool list is frozen). Normally runs automatically on "
    "session start and on config change; call manually only after editing a config.",
    {},
)
_schema(
    "project_mcp_status",
    "Show the current project's MCP config: files found, servers, connection state.",
    {},
)
_schema(
    "project_mcp_add",
    "Add an MCP server to the current project's .hermes/mcp.json, connect it via "
    "the native MCP pipeline; its mcp__<name>__* tools are usable next turn.",
    {
        "name": {"type": "string", "description": "Server name (tools become mcp__<name>__*)"},
        "command": {"type": "string", "description": "stdio: executable to run"},
        "args": {"type": "array", "items": {"type": "string"}, "description": "stdio: command args"},
        "env": {"type": "object", "additionalProperties": {"type": "string"}, "description": "stdio: extra env"},
        "url": {"type": "string", "description": "http: server URL (skip command)"},
        "trust": {"type": "string", "enum": ["full", "untrusted"], "description": "default full (native)"},
        "cwd": {"type": "string", "description": "working dir for the server; ${project} = project root"},
        "lazy": {"type": "boolean", "description": "defer connect to first tool call"},
    },
    ["name"],
)
_schema(
    "project_mcp_remove",
    "Remove an MCP server from the current project's config and disconnect it.",
    {"name": {"type": "string"}},
    ["name"],
)


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _error(message: str, **extra: Any) -> str:
    return _result({"error": message, **extra})


def _cwd() -> str:
    try:
        from agent.runtime_cwd import resolve_agent_cwd
        return str(resolve_agent_cwd())
    except Exception:
        return os.getcwd()


def _enabled(ctx) -> bool:
    try:
        return bool(ctx.get_config("enabled", True))
    except Exception:
        return True


def _load_ledger(ctx) -> dict:
    """{"projects": {path: entry}, "active_project": path} - the full state doc."""
    try:
        doc = ctx.state.get(STATE_KEY, {}) or {}
    except Exception:
        doc = {}
    if not isinstance(doc, dict):
        return {"projects": {}, "active_project": ""}
    if "projects" not in doc:
        doc = {"projects": doc, "active_project": ""}
    doc.setdefault("projects", {})
    doc.setdefault("active_project", "")
    return doc


def _save_ledger(ctx, ledger: dict) -> None:
    try:
        ctx.state.set(STATE_KEY, ledger)
    except Exception:
        logger.warning("project-mcp: failed to persist ledger", exc_info=True)


def _project_entry(ledger: dict, project: str) -> dict:
    return dict(ledger.get("projects", {}).get(project) or {})


def _put_project_entry(ledger: dict, project: str, entry: dict) -> None:
    ledger.setdefault("projects", {})[project] = entry


_SYNC_LOCK = threading.Lock()


def do_sync(ctx, project: Optional[str] = None) -> dict:
    """The real sync. Returns the result payload dict."""
    from .config_source import load_project_config, resolve_project_root, canonical_hash
    if project is None:
        project = resolve_project_root(_cwd())
    config = load_project_config(project)
    if config["errors"]:
        return {
            "project": project,
            "status": "config_error",
            "errors": config["errors"],
            "hint": "fix the JSON; no servers were changed",
        }
    desired = config["servers"]
    ledger = _load_ledger(ctx)
    previous_project = str(ledger.get("active_project") or "")
    entry = _project_entry(ledger, project)
    old_hash = entry.get("hash")
    new_hash = canonical_hash(desired) if desired else ""
    changed = old_hash != new_hash
    current_sig = _project_signature(project)
    with _SYNC_LOCK:
        from . import syncer
        if previous_project and previous_project != project:
            prev_entry = _project_entry(ledger, previous_project)
            syncer.drop_servers(set(prev_entry.get("servers") or {}))
        new_servers, reports, warnings = syncer.apply_sync(desired, dict(entry.get("servers") or {}))
        entry["servers"] = new_servers
        entry["hash"] = new_hash
        entry["sig"] = current_sig
        _put_project_entry(ledger, project, entry)
        ledger["active_project"] = project
        _save_ledger(ctx, ledger)
    if not desired:
        return {
            "project": project,
            "status": "empty",
            "detail": "no project MCP config file found "
                      "(checked .hermes/mcp.json, .mcp.json, .claude/settings.json, .claude/settings.local.json)",
        }
    confirmation_required = old_hash is not None and changed
    return {
        "project": project,
        "status": "synced",
        "changed": changed,
        "confirmation_required": confirmation_required,
        "confirmation_note": (
            "project MCP config changed since last sync; tell the user what changed and that "
            "these servers come from the project directory (they run local commands)"
        ) if confirmation_required else None,
        "tools_are_native": "servers are now native tools mcp__<server>__<tool>; "
                            "call them directly (model-facing list refreshes next turn)",
        "servers": reports,
        "warnings": warnings,
    }


def _config_paths(project: str):
    root = Path(project)
    return (
        root / ".hermes" / "mcp.json",
        root / ".mcp.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
    )


def _project_signature(project: str) -> str:
    """Cheap change probe: names + mtimes of existing config files."""
    parts = []
    for path in _config_paths(project):
        try:
            st = path.stat()
            parts.append(f"{path.name}:{st.st_mtime_ns}:{st.st_size}")
        except FileNotFoundError:
            continue
        except OSError:
            parts.append(f"{path.name}:err")
    return "|".join(parts)


def _has_project_config(project: str) -> bool:
    return any(path.exists() for path in _config_paths(project))


def _maybe_auto_sync(ctx, reason: str) -> Optional[dict]:
    """Sync only when needed; never raises; returns the payload when a sync ran."""
    try:
        if not _enabled(ctx):
            return None
        from .config_source import resolve_project_root
        project = resolve_project_root(_cwd())
        if not _has_project_config(project):
            return None
        sig = _project_signature(project)
        ledger = _load_ledger(ctx)
        entry = _project_entry(ledger, project)
        active = str(ledger.get("active_project") or "")
        if entry.get("sig") == sig and active == project and entry.get("servers"):
            return None
        return do_sync(ctx, project)
    except Exception:
        logger.warning("project-mcp: auto-sync failed", exc_info=True)
        return None


def _make_sync(ctx):
    def _sync(args: dict, **kwargs) -> str:
        return _result(do_sync(ctx))
    return _sync


def _make_status(ctx):
    def _status(args: dict, **kwargs) -> str:
        from .config_source import load_project_config, resolve_project_root
        from tools.mcp_tool_config import _load_mcp_config
        project = resolve_project_root(_cwd())
        config = load_project_config(project)
        from . import syncer
        global_names = set(_load_mcp_config().keys())
        servers = []
        for name in sorted(config["servers"]):
            info = {"name": name, **syncer.server_status(name)}
            if name in global_names:
                info["note"] = (
                    "a server with this name exists in global config; the project copy "
                    "cannot connect until the name is freed")
            servers.append(info)
        return _result({
            "project": project,
            "sources": config["sources"],
            "errors": config["errors"],
            "servers": servers,
        })
    return _status


def _entry_to_config(name: str, args: dict) -> dict:
    cfg: Dict[str, Any] = {}
    if args.get("command"):
        cfg["command"] = str(args["command"])
        if args.get("args"):
            cfg["args"] = [str(a) for a in args["args"]]
        if args.get("env"):
            cfg["env"] = {str(k): str(v) for k, v in args["env"].items()}
    elif args.get("url"):
        cfg["url"] = str(args["url"])
    else:
        raise ValueError("either command or url is required")
    if args.get("trust"):
        cfg["trust"] = str(args["trust"])
    if args.get("cwd"):
        cfg["cwd"] = str(args["cwd"])
    if args.get("lazy") is not None:
        cfg["lazy"] = bool(args["lazy"])
    return cfg


def _write_project_config(project: str, name: str, cfg: dict) -> Path:
    target = Path(project) / ".hermes" / "mcp.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Any] = {}
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
    servers = data.get("mcpServers") if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) else {}
    if not servers and isinstance(data, dict) and data:
        servers = data
    servers[name] = cfg
    target.write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _make_add(ctx):
    def _add(args: dict, **kwargs) -> str:
        name = str(args.get("name") or "").strip()
        if not name or "/" in name or any(c.isspace() for c in name):
            return _error("server name must be non-empty without spaces or slashes")
        try:
            cfg = _entry_to_config(name, args)
        except ValueError as exc:
            return _error(str(exc))
        from .config_source import resolve_project_root
        project = resolve_project_root(_cwd())
        target = Path(project) / ".hermes" / "mcp.json"
        try:
            target = _write_project_config(project, name, cfg)
        except (OSError, ValueError) as exc:
            return _error(f"failed to write {target}: {exc}")
        payload = do_sync(ctx, project)
        payload["written"] = str(target)
        payload["next_turn_note"] = (
            f"server '{name}' is syncing now; its native tools mcp__{name}__* appear in the "
            "model-facing tool list on the NEXT turn")
        return _result(payload)
    return _add


def _make_remove(ctx):
    def _remove(args: dict, **kwargs) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return _error("name is required")
        from .config_source import resolve_project_root
        project = resolve_project_root(_cwd())
        removed_from = []
        for target in (Path(project) / ".hermes" / "mcp.json", Path(project) / ".mcp.json"):
            if not target.exists():
                continue
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            servers = data.get("mcpServers") if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) else None
            if servers is None and isinstance(data, dict):
                servers = data
            if isinstance(servers, dict) and name in servers:
                del servers[name]
                try:
                    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    removed_from.append(str(target))
                except OSError as exc:
                    return _error(f"failed to write {target}: {exc}")
        payload = do_sync(ctx, project)
        payload["removed_from"] = removed_from
        return _result(payload)
    return _remove


def _make_session_start_hook(ctx):
    def _hook(**hook_kwargs):
        _maybe_auto_sync(ctx, "session_start")
        return None
    return _hook


def _make_pre_tool_call_hook(ctx):
    def _hook(**hook_kwargs):
        _maybe_auto_sync(ctx, "pre_tool_call")
        return None
    return _hook


def register(ctx) -> None:
    for hook_name, factory in (
        ("on_session_start", _make_session_start_hook),
        ("pre_tool_call", _make_pre_tool_call_hook),
    ):
        try:
            ctx.register_hook(hook_name, factory(ctx))
        except Exception:
            logger.warning("project-mcp: failed to register %s hook", hook_name, exc_info=True)
    handlers = {
        "project_mcp_sync": _make_sync(ctx),
        "project_mcp_status": _make_status(ctx),
        "project_mcp_add": _make_add(ctx),
        "project_mcp_remove": _make_remove(ctx),
    }
    for name, handler in handlers.items():
        try:
            ctx.register_tool(
                name=name,
                toolset=TOOLSET,
                schema=_SCHEMAS[name],
                handler=handler,
                description=_SCHEMAS[name]["description"],
                emoji="\U0001f4e6",
            )
        except Exception:
            logger.warning("project-mcp: failed to register tool %s", name, exc_info=True)
