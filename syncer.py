"""Connect/disconnect per-project MCP servers through the native pipeline."""

import logging
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

_CORE_ATTRS_OK = True


def _core():
    from tools.mcp_tool_common import _core as core
    return core


def _native_servers() -> Dict[str, dict]:
    from tools.mcp_tool_config import _load_mcp_config
    return _load_mcp_config()


def connected_server_names() -> Set[str]:
    core = _core()
    with core._lock:
        return set(core._servers.keys()) | set(core._lazy_server_configs.keys())


def tool_names_for_server(server: str) -> List[str]:
    core = _core()
    with core._lock:
        return [t for t, s in core._mcp_tool_server_names.items() if s == server]


def server_status(name: str) -> dict:
    core = _core()
    with core._lock:
        server = core._servers.get(name)
        lazy = name in core._lazy_server_configs
        error = core._server_connect_errors.get(name)
    if server is not None and server.session is not None:
        return {"status": "connected", "tools": len(getattr(server, "_registered_tool_names", []))}
    if server is not None and server._is_recycled_stdio():
        return {"status": "connected", "tools": len(getattr(server, "_registered_tool_names", []))}
    if error:
        return {"status": "failed", "error": error}
    if lazy:
        return {"status": "lazy", "tools": 0}
    return {"status": "configured", "tools": 0}


def _shutdown_server(name: str) -> None:
    core = _core()
    loop_running = True
    try:
        from tools.mcp_tool_loop import _running_loop
        loop_running = _running_loop() is not None
    except Exception:
        loop_running = False
    server = None
    with core._lock:
        server = core._servers.get(name)
    if server is None:
        with core._lock:
            core._lazy_server_configs.pop(name, None)
        return
    if loop_running:
        from tools.mcp_tool_loop import _run_on_mcp_loop
        _run_on_mcp_loop(lambda: server.shutdown(), timeout=30)
    else:
        logger.warning("project-mcp: MCP loop not running; cannot shut down server %s", name)


def call_tool(server: str, tool: str, arguments: Dict[str, Any], timeout: float = 60.0) -> str:
    from tools.mcp_tool_handlers import _make_tool_handler
    return _make_tool_handler(server, tool, timeout)(dict(arguments or {}))


def apply_sync(
    desired: Dict[str, dict],
    ledger_servers: Dict[str, str],
) -> Tuple[Dict[str, str], List[dict], List[str]]:
    """Diff desired config against the plugin ledger; connect and disconnect.

    Returns (new_ledger, per_server_reports, warnings).
    """
    from tools.mcp_tool_discovery import register_mcp_servers
    from hermes_cli.mcp_security import validate_mcp_server_entry
    from config_source import canonical_hash

    warnings: List[str] = []
    reports: List[dict] = []
    native = set(_native_servers().keys())
    new_ledger: Dict[str, str] = {}

    conflicts = sorted(set(desired) & native)
    if conflicts:
        warnings.append(
            "project servers conflict with global config names and are skipped: "
            + ", ".join(conflicts))

    to_connect: Dict[str, dict] = {}
    for name, cfg in desired.items():
        if name in native:
            continue
        issues = validate_mcp_server_entry(name, cfg if isinstance(cfg, dict) else {})
        if issues:
            warnings.append(f"server '{name}' rejected: {'; '.join(issues)}")
            reports.append({"name": name, "status": "rejected", "error": "; ".join(issues)})
            continue
        if not isinstance(cfg, dict) or not (cfg.get("command") or cfg.get("url")):
            warnings.append(f"server '{name}' has neither command nor url; skipped")
            reports.append({"name": name, "status": "invalid"})
            continue
        fingerprint = canonical_hash(cfg)
        previous = ledger_servers.get(name)
        connected_now = name in connected_server_names()
        if connected_now and previous == fingerprint:
            new_ledger[name] = fingerprint
            reports.append({"name": name, **server_status(name), "unchanged": True})
            continue
        if connected_now and previous != fingerprint and name in ledger_servers:
            _shutdown_server(name)
        to_connect[name] = cfg

    stale = [n for n in ledger_servers if n not in desired]
    for name in stale:
        if name in connected_server_names():
            _shutdown_server(name)
            reports.append({"name": name, "status": "disconnected", "reason": "removed from project config"})
        else:
            reports.append({"name": name, "status": "forgotten"})

    if to_connect:
        try:
            register_mcp_servers(to_connect)
        except Exception as exc:
            warnings.append(f"connect pass failed: {exc}")
        for name, cfg in to_connect.items():
            status = server_status(name)
            reports.append({"name": name, **status})
            if status["status"] == "connected":
                new_ledger[name] = canonical_hash(cfg)
            elif status["status"] == "lazy":
                new_ledger[name] = canonical_hash(cfg)
            else:
                warnings.append(f"server '{name}' did not reach connected state")

    return new_ledger, reports, warnings
