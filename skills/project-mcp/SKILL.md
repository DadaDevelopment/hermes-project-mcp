# Project MCP

Use when the session needs MCP servers that belong to the current PROJECT
(not global config), or when the user mentions `.mcp.json`, `.claude`,
project-local MCP setup, or asks what MCP servers a project has.

## Behavior

- Project = git root of the session cwd, else the cwd itself.
- Config files (later wins per server name):
  `.claude/settings.json` < `.claude/settings.local.json` < `.mcp.json` <
  `.hermes/mcp.json`. All use the `{"mcpServers": {...}}` shape; a bare
  object of servers also works.
- Project servers are NATIVE MCP servers: after sync their tools are
  `mcp__<server>__<tool>` and are called directly, like any global MCP tool.
  No wrapper, no proxy.
- Sync happens automatically: once when a session starts in a project with a
  config, and lazily before the next tool call whenever the config files
  change (mtime probe) or the session moves to another project. Switching
  projects disconnects exactly the previous project's servers; global ones
  stay.
- `project_mcp_sync` forces a rescan now - use after editing a config file,
  or when project tools are missing from the tool list mid-turn (the
  model-facing tool list refreshes next turn; within the same turn use the
  server via its tool name and it will resolve on the next turn).
- `project_mcp_status` answers "what MCP servers does this project have".
- `project_mcp_add` / `project_mcp_remove` edit `.hermes/mcp.json` and sync
  in one step. Prefer them over editing the file by hand when the user asks
  in chat.
- Project servers default to `trust: full` like global ones (native rule).
  For third-party configs recommend `"trust": "untrusted"` on the server
  entry: write-capable tools then require per-call approval.
- If sync reports `confirmation_required`, tell the user what changed before
  calling project servers.
- Servers from the project directory run LOCAL COMMANDS from that directory.
  Never paste server configs from untrusted repos without saying so.
- A project server whose name equals a global server is skipped (global
  wins) and noted by project_mcp_status.
- Synced project servers are mirrored into config.yaml (marked with
  `_project_mcp`) so the dashboard/CLI show them as first-class servers.
  The active project's servers are enabled; other projects' show as
  disabled. Do not hand-edit mirrored entries - manage them via the
  project file or project_mcp_add/remove.

## File format example

```json
{
  "mcpServers": {
    "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
    "api": {"url": "http://127.0.0.1:8080/mcp"},
    "builder": {"command": "node", "args": ["server.js"], "cwd": "${project}/tools"}
  }
}
```

`${project}` expands to the project root; relative `cwd`/paths resolve
against it.
