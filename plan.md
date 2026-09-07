# plan: hermes-project-mcp

Author: Hermes fork session
Status: accepted
Date: 2026-09-07

## Modules

```
hermes-project-mcp/
  plugin.yaml          kind: standalone, provides_tools x5
  __init__.py          register(ctx): 5 tools + on_session_start hook
  config_source.py     project discovery + file parsing + merge + hash
  syncer.py            connect/disconnect via native mcp_tool pipeline
  skills/
    project-mcp/SKILL.md
```

## Riskiest steps first

1. `syncer` calls into `tools.mcp_tool_discovery` from plugin code. Risk:
   import-time side effects. Mitigation: all imports inside functions (the
   a2a plugin does the same); the MCP SDK and loop are already running in
   the gateway process by the time any tool fires.
2. Disconnect-on-resync: only shut down servers that (a) were previously
   synced by THIS plugin for THIS project (tracked via ctx.state keyed by
   project path), (b) disappeared or changed. Never touch servers not owned
   by us (global config, other plugins). Ownership check:
   `tools.mcp_tool._core._mcp_tool_server_names` + a plugin-side ledger of
   synced server names per project.
3. `pre_tool_call` hook must be fast and never raise (core treats exceptions
   as "no directive" but logs). Only do work when tool_name starts with
   `mcp__`; check sync-needed flags in memory, delegate actual resync to the
   next tool call - never connect servers inside the hook.

## Sequence per tool call

handler -> _resolve_project() (runtime_cwd.resolve_agent_cwd -> git root)
        -> _load_merged(project) with per-file parse errors collected
        -> _sync(project, merged): diff vs ledger; register_mcp_servers(new
           or changed); shutdown(removed); update ledger + config hash
        -> json result.

## State (ctx.state, quota 10MB - fine)

- key `projects` -> {project_path: {"hash": <merged-config-sha1>,
    "servers": {name: <fingerprint-sha1>}}}
Config hash = sha1 of canonical json of merged servers. Server fingerprint =
sha1 of that server's config dict (no env interpolation - interpolation is
applied by the native loader at connect time anyway).

## Tests (local, no gateway)

- unit: config_source parsing (all 4 file shapes + merge order + ${project})
- unit: sync diff logic against a fake registry (monkeypatched module funcs)
- live: real hermes -z run in a temp project with a trivial stdio server
  (python -c based MCP server? No - use `uvx mcp-server-fetch`-style? NO
  network flakiness: write a 20-line python MCP stdio server using the mcp
  SDK already in /opt/hermes/.venv)

## Rejected alternatives

- Custom MCP client in the plugin: duplicates trust/breaker/keepalive logic.
  Rejected - native pipeline already does it.
- Patching core `_load_mcp_config` to include project files: invasive,
  restart-bound, global namespace pollution. Rejected.
- per_tool CallTool via ctx.call_mcp: requires per-server allowlist in global
  config (restart for every new project server). Rejected as primary path;
  project_mcp_call uses the native handler directly instead, which does not
  consult the plugin allowlist (same trust gates apply).

## Open risks

- Registry "mcp-* toolsets are exempt" deregistration path: verified
  _deregister_tools uses registry.deregister with server scope; our synced
  servers adopt the same scope machinery, so dereg on shutdown is real.
- Desktop sessions have no git root -> project = cwd itself. Fine.
