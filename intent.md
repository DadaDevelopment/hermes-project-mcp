# intent: hermes-project-mcp plugin

Author: Hermes fork session
Status: done
Date: 2026-09-07

## Problem (owner's words)

"сделать per-project mcp как в claude code; настройка через desktop/ui/конфиг/
+ аналог /path/to/project/.claude папочки"

## Incident log

1. v0.1.0: project_mcp_call proxy + manual-only sync. Owner: "это костыль,
   агент должен честно видеть и вызывать нативные тулы". -> v0.2.0 native-first
   (hooks auto-sync, no proxy).
2. v0.3.0: dashboard visibility via core patch (web_routers/mcp.py merge +
   bridge module). Owner: "нет, никаких патчей - неужели нельзя нормально?".
   -> v0.4.0.

## v0.4.0: config mirror (the "normal" way)

Project servers are materialized into config.yaml mcp_servers with a
`_project_mcp` marker (project path). Semantics:

- Active project's mirrored entries: enabled:true -> they are FIRST-CLASS
  configured servers: dashboard MCP page, `hermes mcp list`, session info
  panel, banner - every surface shows them natively, no special casing.
- Other projects' mirrored entries: enabled:false (native discovery skips
  them; UI shows them disabled = "another project's").
- Project switch flips the flags; server removed from the project file ->
  its config entry is dropped on next sync; `project_mcp_remove` removes from
  project file AND config; UI Delete removes the config entry (next sync
  re-adds only if the project file still declares it).
- Global config.yaml servers are never touched (marker identifies ours).
- No core files modified, no manifest bridge, no image-layer state.

## Verification

- config_mirror unit: 6/6 (marker write, switch disables, re-enable,
  drop-on-remove, global untouched, drop_project)
- plugin suite: 9/9 (test-project-mcp-v2.py)
- live: dashboard /api/mcp/servers lists mirrored project server natively
- patch fully reverted from /opt/hermes (stock web_routers/mcp.py restored,
  bridge module removed)

## Progress checklist

- [x] audit -> spec -> plan -> v1 -> v2 (native-first)
- [x] v0.3.0 UI (patched) -> REJECTED -> reverted
- [x] v0.4.0 config mirror, unit 6/6 + suite 9/9
- [x] installed, doctor clean, live UI check
