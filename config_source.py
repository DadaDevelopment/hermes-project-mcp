"""Project discovery and per-project MCP config file parsing."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_DIRNAME = ".hermes"
CONFIG_FILENAME = "mcp.json"
CLAUDE_DIRNAME = ".claude"
CLAUDE_FILES = ("settings.json", "settings.local.json")
CLAUDE_ROOT_FILE = ".mcp.json"

MAX_FILE_BYTES = 256 * 1024


def resolve_project_root(cwd: str) -> str:
    """Git root of *cwd* when inside a repo, else the cwd itself."""
    probe = Path(cwd).expanduser()
    if not probe.is_dir():
        return str(probe)
    current = probe.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return str(candidate)
    return str(current)


def _read_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"{path}: {exc}"
    if len(raw) > MAX_FILE_BYTES:
        return None, f"{path}: file exceeds {MAX_FILE_BYTES} bytes"
    try:
        return json.loads(raw.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"{path}: invalid JSON: {exc}"


def _extract_servers(data: Any, source: str, errors: List[str]) -> Dict[str, dict]:
    if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
        return {str(k): v for k, v in data["mcpServers"].items()}
    if isinstance(data, dict) and "servers" in data:
        return {}
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    errors.append(f"{source}: no mcpServers object found")
    return {}


def _sources_for(project: str) -> List[Tuple[str, Path]]:
    root = Path(project)
    sources: List[Tuple[str, Path]] = []
    claude_dir = root / CLAUDE_DIRNAME
    for rel in CLAUDE_FILES:
        sources.append((f"{CLAUDE_DIRNAME}/{rel}", claude_dir / rel))
    sources.append((CLAUDE_ROOT_FILE, root / CLAUDE_ROOT_FILE))
    sources.append((f"{CONFIG_DIRNAME}/{CONFIG_FILENAME}", root / CONFIG_DIRNAME / CONFIG_FILENAME))
    return sources


def _expand_project(value: Any, project: str) -> Any:
    if isinstance(value, str):
        if "${project}" in value:
            return value.replace("${project}", project)
        if value.startswith("./") or value.startswith("../"):
            return os.path.normpath(os.path.join(project, value))
        return value
    if isinstance(value, dict):
        return {k: _expand_project(v, project) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_project(v, project) for v in value]
    return value


def load_project_config(project: str) -> Dict[str, Any]:
    """Merged per-project MCP config plus diagnostics.

    Returns {"project", "sources": [{source, found, servers|error}],
    "servers": {name: config}, "errors": []}.
    """
    errors: List[str] = []
    sources_report: List[dict] = []
    merged: Dict[str, dict] = {}
    for source, path in _sources_for(project):
        data, err = _read_json(path)
        if data is None and err is None:
            sources_report.append({"source": source, "found": False})
            continue
        if err is not None:
            errors.append(err)
            sources_report.append({"source": source, "found": True, "error": err})
            continue
        servers = _extract_servers(data, source, errors)
        sources_report.append({"source": source, "found": True, "servers": sorted(servers)})
        merged.update(servers)
    return {
        "project": project,
        "sources": sources_report,
        "servers": {name: _expand_project(cfg, project) for name, cfg in merged.items()},
        "errors": errors,
    }


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()
