"""UI visibility for per-project MCP servers.

Reads the manifest written by the project-mcp plugin on every sync and
appends its servers to the dashboard ``/api/mcp/servers`` payload, marked
with ``scope: project`` (plus the project path). Global servers always come
first and keep their original shape; a missing/corrupt manifest is a no-op.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_MANIFEST_GLOB = "agent-plugin-project-mcp-*/manifest.json"


def _find_manifest() -> Path | None:
    try:
        from hermes_constants import get_hermes_home
        base = Path(get_hermes_home()) / "plugin-data"
    except Exception:
        return None
    if not base.is_dir():
        return None
    candidates = [p for p in base.glob(_MANIFEST_GLOB) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _project_server_entries() -> List[Dict[str, Any]]:
    """Servers from the freshest project-mcp manifest, UI-safe summary shape."""
    manifest = _find_manifest()
    if manifest is None:
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.debug("project-mcp manifest unreadable: %s", manifest)
        return []
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list):
        return []
    entries: List[Dict[str, Any]] = []
    for project in projects:
        if not isinstance(project, dict):
            continue
        project_path = str(project.get("path") or "")
        servers = project.get("servers") if isinstance(project.get("servers"), dict) else {}
        for name, summary in servers.items():
            if not isinstance(summary, dict):
                continue
            entry = dict(summary)
            entry["name"] = str(name)
            entry["scope"] = "project"
            if project_path:
                entry["project"] = project_path
            entries.append(entry)
    return entries


def append_project_servers(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge project-scope servers into an /api/mcp/servers payload (list of summaries).

    Project entries never override a global server with the same name; both
    stay, the global first (SPA keys rows by name, the project copy is
    suffixed ' (project)' in a separate display field the SPA can ignore).
    """
    try:
        project_entries = _project_server_entries()
    except Exception:
        logger.debug("project-mcp UI merge failed", exc_info=True)
        return servers
    if not project_entries:
        return servers
    existing = {str(s.get("name")) for s in servers}
    merged = list(servers)
    seen = set()
    for entry in project_entries:
        name = entry["name"]
        if name in existing or name in seen:
            continue
        seen.add(name)
        merged.append(entry)
    return merged
