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
- After creating or editing any of those files, call `project_mcp_sync`.
  The tools become native tools named `mcp__<server>__<tool>`.
- `project_mcp_status` answers "what MCP servers does this project have".
- `project_mcp_add` / `project_mcp_remove` edit `.hermes/mcp.json` and sync
  in one step. Prefer them over editing the file by hand when the user asks
  in chat.
- `project_mcp_call(server, tool, arguments)` is the fallback when the
  native `mcp__` tool is not in the current tool list (tool list is frozen
  per turn). Prefer the native tool when present.
- Project servers default to `trust: untrusted`: write-capable tools ask the
  user for approval at call time. Do not set `trust: full` without the
  user asking for it.
- If sync reports `confirmation_required`, tell the user what changed before
  calling project servers.
- Servers from the project directory run LOCAL COMMANDS from that directory.
  Never paste server configs from untrusted repos without saying so.

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
