"""Apply the dashboard /api/mcp/servers UI merge patch (idempotent)."""

import sys

sys.path.insert(0, "/opt/data/plugins/project-mcp")

from dashboard_patch import BRIDGE_MODULE, ORIGINAL, PATCHED

BRIDGE_TARGET = "/opt/hermes/hermes_cli/project_mcp_ui_bridge.py"
ROUTER_TARGET = "/opt/hermes/hermes_cli/web_routers/mcp.py"


def main() -> int:
    src = open(ROUTER_TARGET).read()
    if PATCHED.strip() in src:
        print("already patched")
    elif ORIGINAL.strip() in src:
        open(ROUTER_TARGET, "w").write(src.replace(ORIGINAL.strip(), PATCHED.strip()))
        print("mcp.py patched")
    else:
        print("stock list_mcp_servers not found - upstream changed; NOT patching")
        return 1
    open(BRIDGE_TARGET, "w").write(BRIDGE_MODULE)
    print("bridge module installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
