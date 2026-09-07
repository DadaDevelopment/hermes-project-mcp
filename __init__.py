"""Per-project MCP servers: Claude-Code-style .mcp.json / .hermes/mcp.json support."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOOLSET = "project-mcp"
STATE_KEY = "projects"

_SCHEMAS: Dict[str, dict] = {}


def _schema(name: str, description: str, properties: dict, required: Optional[list] = None) -> None:
    params = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    _SCHEMAS[name] = {"name": name, "description": description, "parameters": params}


_schema(
    "project_mcp_sync",
    "Connect/disconnect the current project's MCP servers (from .hermes/mcp.json, "
    ".mcp.json, .claude/settings*.json). Run after editing any of those files; also "
    "run it once when a project's MCP tools are needed.",
    {},
)
_schema(
    "project_mcp_status",
    "Show the current project's MCP config: files found, servers, connection state.",
    {},
)
_schema(
    "project_mcp_add",
    "Add an MCP server to the current project's .hermes/mcp.json and sync it.",
    {
        "name": {"type": "string", "description": "Server name (tool prefix mcp__<name>__)"},
        "command": {"type": "string", "description": "stdio: executable to run"},
        "args": {"type": "array", "items": {"type": "string"}, "description": "stdio: command args"},
        "env": {"type": "object", "additionalProperties": {"type": "string"}, "description": "stdio: extra env"},
        "url": {"type": "string", "description": "http: server URL (skip command)"},
        "trust": {"type": "string", "enum": ["full", "untrusted"], "description": "default untrusted"},
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
_schema(
    "project_mcp_call",
    "Call a tool on a project MCP server by name (escape hatch when the native "
    "mcp__<server>__<tool> tool is not loaded in the current tool list).",
    {
        "server": {"type": "string"},
        "tool": {"type": "string"},
        "arguments": {"type": "object", "additionalProperties": True},
        "timeout": {"type": "number", "description": "seconds, default 60"},
    },
    ["server", "tool"],
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
    try:
        return dict(ctx.state.get(STATE_KEY, {}) or {})
    except Exception:
        return {}


def _save_ledger(ctx, ledger: dict) -> None:
    try:
        ctx.state.set(STATE_KEY, ledger)
    except Exception:
        logger.warning("project-mcp: failed to persist ledger", exc_info=True)


def _project_entry(ledger: dict, project: str) -> dict:
    return dict(ledger.get(project) or {})


def _make_sync(ctx):
    def _sync(args: dict, **kwargs) -> str:
        if not _enabled(ctx):
            return _error("project-mcp plugin is disabled (plugins.entries.project-mcp.settings.enabled)")
        from config_source import load_project_config, resolve_project_root, canonical_hash
        project = resolve_project_root(_cwd())
        config = load_project_config(project)
        if config["errors"]:
            return _result({
                "project": project,
                "status": "config_error",
                "errors": config["errors"],
                "hint": "fix the JSON and call project_mcp_sync again; no servers were changed",
            })
        desired = config["servers"]
        if not desired:
            return _result({
                "project": project,
                "status": "empty",
                "detail": "no project MCP config file found "
                          "(checked .hermes/mcp.json, .mcp.json, .claude/settings.json, .claude/settings.local.json)",
            })
        ledger = _load_ledger(ctx)
        entry = _project_entry(ledger, project)
        old_hash = entry.get("hash")
        new_hash = canonical_hash(desired)
        import syncer
        new_servers, reports, warnings = syncer.apply_sync(desired, dict(entry.get("servers") or {}))
        entry["servers"] = new_servers
        entry["hash"] = new_hash
        ledger[project] = entry
        _save_ledger(ctx, ledger)
        confirmation_required = old_hash is not None and old_hash != new_hash
        return _result({
            "project": project,
            "status": "synced",
            "confirmation_required": confirmation_required,
            "confirmation_note": (
                "project MCP config changed since last sync; tell the user what changed and that "
                "these servers come from the project directory (they run local commands)"
            ) if confirmation_required else None,
            "servers": reports,
            "warnings": warnings,
        })
    return _sync


def _make_status(ctx):
    def _status(args: dict, **kwargs) -> str:
        from config_source import load_project_config, resolve_project_root
        project = resolve_project_root(_cwd())
        config = load_project_config(project)
        import syncer
        servers = []
        for name in sorted(config["servers"]):
            native_conflict = name in syncer.connected_server_names() and name not in (
                _project_entry(_load_ledger(ctx), project).get("servers") or {})
            info = {"name": name, **syncer.server_status(name)}
            if native_conflict:
                info["note"] = "a server with this name is connected from global config"
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


def _make_add(ctx):
    def _add(args: dict, **kwargs) -> str:
        name = str(args.get("name") or "").strip()
        if not name or "/" in name or any(c.isspace() for c in name):
            return _error("server name must be non-empty without spaces or slashes")
        try:
            cfg = _entry_to_config(name, args)
        except ValueError as exc:
            return _error(str(exc))
        from config_source import resolve_project_root
        project = resolve_project_root(_cwd())
        target = Path(project) / ".hermes" / "mcp.json"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if target.exists():
                data = json.loads(target.read_text(encoding="utf-8"))
            servers = data.get("mcpServers") if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict) else {}
            if not servers and isinstance(data, dict) and data:
                servers = data
            servers[name] = cfg
            data = {"mcpServers": servers}
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError) as exc:
            return _error(f"failed to write {target}: {exc}")
        sync = _make_sync(ctx)
        sync_result = json.loads(sync({}, **kwargs))
        return _result({"written": str(target), "config": cfg, "sync": sync_result})
    return _add


def _make_remove(ctx):
    def _remove(args: dict, **kwargs) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            return _error("name is required")
        from config_source import resolve_project_root
        project = resolve_project_root(_cwd())
        removed_from = []
        candidates = [
            Path(project) / ".hermes" / "mcp.json",
            Path(project) / ".mcp.json",
        ]
        for target in candidates:
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
        sync = _make_sync(ctx)
        sync_result = json.loads(sync({}, **kwargs))
        return _result({"removed_from": removed_from, "sync": sync_result})
    return _remove


def _make_call(ctx):
    def _call(args: dict, **kwargs) -> str:
        server = str(args.get("server") or "").strip()
        tool = str(args.get("tool") or "").strip()
        if not server or not tool:
            return _error("server and tool are required")
        from config_source import load_project_config, resolve_project_root
        project = resolve_project_root(_cwd())
        config = load_project_config(project)
        if server not in config["servers"]:
            known = sorted(config["servers"])
            return _error(f"server '{server}' is not defined in this project's MCP config", known=known)
        import syncer
        status = syncer.server_status(server)
        if status["status"] not in ("connected", "lazy"):
            sync = _make_sync(ctx)
            sync({}, **kwargs)
            status = syncer.server_status(server)
        if status["status"] not in ("connected", "lazy"):
            return _error(f"server '{server}' is not connected", status=status)
        timeout = args.get("timeout")
        try:
            timeout_f = min(max(float(timeout), 1.0), 600.0) if timeout else 60.0
        except (TypeError, ValueError):
            timeout_f = 60.0
        raw = syncer.call_tool(server, tool, args.get("arguments") or {}, timeout_f)
        return raw if isinstance(raw, str) else _result({"result": raw})
    return _call


def register(ctx) -> None:
    handlers = {
        "project_mcp_sync": _make_sync(ctx),
        "project_mcp_status": _make_status(ctx),
        "project_mcp_add": _make_add(ctx),
        "project_mcp_remove": _make_remove(ctx),
        "project_mcp_call": _make_call(ctx),
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
