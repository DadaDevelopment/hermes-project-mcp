# Dashboard UI integration

The dashboard MCP page (and anything reading `GET /api/mcp/servers`) shows
project servers too, merged after the global ones with `scope: "project"`
and the originating `project` path.

## How it works

1. On every sync the plugin writes `manifest.json` next to its plugin state
   (`$HERMES_HOME/plugin-data/agent-plugin-project-mcp-*/manifest.json`):
   `{"updated_at": ms, "projects": [{path, servers: {name: {transport, url|
   command, args, enabled, trust, project, scope}}}]}`.
2. A one-file core patch teaches `web_routers/mcp.py` to append the
   manifest's servers to the list via `hermes_cli/project_mcp_ui_bridge.py`
   (missing/corrupt manifest = no-op; global names always win duplicates).

## Applying the patch (idempotent)

```bash
docker exec -u root hermes /opt/hermes/.venv/bin/python /opt/data/plugins/project-mcp/scripts/apply_ui_patch.py
docker exec hermes /package/admin/s6/command/s6-svc -t /run/service/dashboard
```

`scripts/apply_ui_patch.py` re-reads `dashboard_patch.py` from the plugin
directory: safe to re-run after a Hermes image update (it either reports
"already patched" or re-applies over the stock handler; on an upstream
rewrite of `list_mcp_servers` it aborts instead of guessing).

## Honest limits

- The patch lives in the container's image layer: a Hermes image upgrade
  wipes it until re-applied (the command above).
- The SPA renders the standard fields (name/transport/command/args); the
  `project`/`scope` extras ride in the payload for future UI work and the
  API consumer.
