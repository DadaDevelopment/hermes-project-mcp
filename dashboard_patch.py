"""The exact edit applied to /opt/hermes/hermes_cli/web_routers/mcp.py (dashboard UI merge).

Kept in the plugin repo so the one-file core change is reviewable and
re-appliable after a Hermes image update. Applied to the live install by
scripts/apply-dashboard-patch.sh (idempotent).
"""

PATCHED = '''@router.get("/api/mcp/servers")
async def list_mcp_servers(profile: Optional[str] = None):
    from hermes_cli.mcp_config import _get_mcp_servers

    servers = await scoped_to_thread(profile, _get_mcp_servers)
    payload = [_mcp_server_summary(name, cfg) for name, cfg in sorted(servers.items())]
    try:
        from hermes_cli.project_mcp_ui_bridge import append_project_servers
        payload = append_project_servers(payload)
    except Exception:
        _log.debug("project-mcp UI merge skipped", exc_info=True)
    return {"servers": payload}
'''

ORIGINAL = '''@router.get("/api/mcp/servers")
async def list_mcp_servers(profile: Optional[str] = None):
    from hermes_cli.mcp_config import _get_mcp_servers

    servers = await scoped_to_thread(profile, _get_mcp_servers)
    return {"servers": [_mcp_server_summary(name, cfg) for name, cfg in sorted(servers.items())]}
'''

BRIDGE_MODULE = """\"\"\"project-mcp UI bridge (installed by hermes-project-mcp).

Appends per-project MCP servers (from the project-mcp plugin's manifest) to
the dashboard /api/mcp/servers payload. Missing manifest = no-op.
\"\"\"

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MANIFEST_GLOB = "agent-plugin-project-mcp-*/manifest.json"


def _find_manifest():
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


def _project_server_entries():
    manifest = _find_manifest()
    if manifest is None:
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list):
        return []
    entries = []
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


def append_project_servers(servers):
    try:
        project_entries = _project_server_entries()
    except Exception:
        return servers
    if not project_entries:
        return servers
    existing = {str(s.get("name")) for s in servers}
    merged = list(servers)
    seen = set()
    for entry in project_entries:
        name = entry.get("name")
        if not name or name in existing or name in seen:
            continue
        seen.add(name)
        merged.append(entry)
    return merged
"""
