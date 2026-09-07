"""Mirror project servers into config.yaml so every UI/CLI surface sees them.

Each mirrored entry carries a ``_project_mcp`` marker (project path + origin
file). Enabled flag encodes scoping: the active project's servers are
enabled, other projects' mirrored entries are enabled:false (native discovery
skips disabled servers; the UI shows them grayed out as "other project").
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MARKER_KEY = "_project_mcp"


def _load() -> Dict[str, Any]:
    from hermes_cli.config import load_config
    return load_config() or {}


def _save(config: Dict[str, Any]) -> None:
    from hermes_cli.config import save_config
    save_config(config)


def _is_ours(name: str, cfg: Any, project: str | None = None) -> bool:
    if not isinstance(cfg, dict) or not isinstance(cfg.get(MARKER_KEY), dict):
        return False
    if project is None:
        return True
    return str(cfg[MARKER_KEY].get("project") or "") == project


def mirror(
    project: str,
    active_servers: Dict[str, dict],
    ledger_servers: Dict[str, str],
) -> List[str]:
    """Sync config.yaml with the project's desired servers.

    - desired servers: written (marker + project path), enabled true
    - other projects' mirrored entries: enabled false
    - our marker'd entries for THIS project no longer desired: removed
    Returns mirrored server names.
    """
    config = _load()
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        servers = {}
    changed = False

    for name, cfg in list(servers.items()):
        if not _is_ours(name, cfg):
            continue
        entry_project = str(cfg[MARKER_KEY].get("project") or "")
        if entry_project == project:
            if name not in active_servers:
                del servers[name]
                changed = True
                logger.info("project-mcp: config mirror dropped %s (no longer in project config)", name)
            elif cfg.get("enabled", True) is False:
                cfg["enabled"] = True
                changed = True
        elif cfg.get("enabled", True) is not False:
            cfg["enabled"] = False
            changed = True

    for name, cfg in active_servers.items():
        if name in servers and not _is_ours(name, servers[name]):
            continue
        mirrored = dict(cfg)
        mirrored[MARKER_KEY] = {"project": project, "ledger_fingerprint": ledger_servers.get(name, "")}
        mirrored["enabled"] = True
        if servers.get(name) != mirrored:
            servers[name] = mirrored
            changed = True

    config["mcp_servers"] = servers
    if changed:
        _save(config)
    return [n for n, c in servers.items() if _is_ours(n, c, project)]


def drop_project(project: str) -> List[str]:
    """Remove every mirrored entry of *project* (project deleted / switched away)."""
    config = _load()
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return []
    removed = []
    for name, cfg in list(servers.items()):
        if _is_ours(name, cfg, project):
            del servers[name]
            removed.append(name)
    if removed:
        config["mcp_servers"] = servers
        _save(config)
        logger.info("project-mcp: config mirror dropped %s for %s", removed, project)
    return removed
