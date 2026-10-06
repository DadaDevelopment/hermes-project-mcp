"""Regression: per-project ``disabledServers`` veto for global MCP servers."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PACKAGE = "project_mcp_under_test"


def _load_plugin() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        PACKAGE, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin() -> ModuleType:
    return _load_plugin()


@pytest.fixture(scope="module")
def source(plugin) -> ModuleType:
    return importlib.import_module(f"{PACKAGE}.config_source")


class _Ctx:
    """Minimal plugin context: default config, empty state."""

    def get_config(self, _key, default=None):
        return default


def _write(root: Path, payload: dict) -> None:
    (root / ".hermes").mkdir(parents=True, exist_ok=True)
    (root / ".hermes" / "mcp.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    _write(root, {"mcpServers": {"jenkins-ses": {"url": "http://x"}},
                  "disabledServers": ["jenkins", "dada-cloud"]})
    (root / "submodule" / ".git").mkdir(parents=True)
    return root


@pytest.mark.parametrize("tool,blocked", [
    ("mcp__jenkins__getJob", True),
    ("mcp__dada_cloud__listApps", True),
    ("mcp__jenkins_ses__getJob", False),
    ("mcp__ticktick__search", False),
    ("terminal", False),
])
def test_veto_in_project_root(plugin, project, monkeypatch, tool, blocked):
    monkeypatch.setattr(plugin, "_cwd", lambda: str(project))
    result = plugin._disabled_server_block(_Ctx(), tool)
    assert (result is not None and result["action"] == "block") is blocked


def test_submodule_inherits_parent_switch_offs(plugin, project, monkeypatch):
    monkeypatch.setattr(plugin, "_cwd", lambda: str(project / "submodule"))
    assert plugin._disabled_server_block(_Ctx(), "mcp__jenkins__getJob") is not None


def test_other_project_unaffected(plugin, tmp_path, monkeypatch):
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    monkeypatch.setattr(plugin, "_cwd", lambda: str(other))
    assert plugin._disabled_server_block(_Ctx(), "mcp__jenkins__getJob") is None


def test_disabled_key_is_not_a_server_in_flat_layout(source, project):
    _write(project, {"jenkins-ses": {"url": "http://x"}, "disabledServers": ["jenkins"]})
    assert sorted(source.load_project_config(str(project))["servers"]) == ["jenkins-ses"]
    assert source.load_disabled_servers(str(project)) == ["jenkins"]


def test_claude_settings_keys_are_not_servers(source, project):
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"$comment": "x", "hooks": {}, "permissions": {"allow": []}}), encoding="utf-8")
    assert sorted(source.load_project_config(str(project))["servers"]) == ["jenkins-ses"]
