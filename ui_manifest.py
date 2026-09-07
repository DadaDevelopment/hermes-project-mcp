"""Write the UI-facing manifest consumed by the dashboard /api/mcp/servers merge."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.json"


def _ui_safe_summary(name: str, cfg: dict, project: str) -> Dict[str, Any]:
    del name
    transport = "http" if cfg.get("url") else ("stdio" if cfg.get("command") else "unknown")
    summary: Dict[str, Any] = {
        "transport": transport,
        "url": cfg.get("url"),
        "command": cfg.get("command"),
        "args": list(cfg.get("args") or []),
        "enabled": cfg.get("enabled", True) is not False,
        "trust": cfg.get("trust") or "full",
        "project": project,
        "scope": "project",
    }
    env = cfg.get("env")
    if isinstance(env, dict) and env:
        summary["env_keys"] = sorted(str(k) for k in env)
    return summary


def write_manifest(state_dir: Path, ledger: dict) -> None:
    """Atomically write manifest.json next to the plugin state file.

    Shape: {"updated_at": ms, "projects": [{path, servers: {name: summary}}]}.
    Best-effort: any failure is logged and swallowed - the manifest is a
    display aid, never a source of truth for syncing.
    """
    projects_out = []
    projects = ledger.get("projects") if isinstance(ledger, dict) else {}
    for project, entry in (projects or {}).items():
        if not isinstance(project, str) or not isinstance(entry, dict):
            continue
        servers = entry.get("servers") if isinstance(entry.get("servers"), dict) else {}
        if not servers:
            continue
        configs = entry.get("configs") if isinstance(entry.get("configs"), dict) else {}
        servers_out = {}
        for name, fingerprint in servers.items():
            cfg = configs.get(name)
            servers_out[name] = (
                _ui_safe_summary(name, cfg, project) if isinstance(cfg, dict)
                else {"transport": "unknown", "project": project, "scope": "project"})
        projects_out.append({"path": project, "servers": servers_out})
    payload = {"updated_at": int(time.time() * 1000), "projects": projects_out}
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        target = state_dir / _MANIFEST_NAME
        tmp = state_dir / (_MANIFEST_NAME + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        logger.warning("project-mcp: failed to write UI manifest", exc_info=True)
