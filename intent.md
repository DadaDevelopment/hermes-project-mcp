# intent: hermes-project-mcp plugin

Author: Hermes fork session
Status: in-progress
Date: 2026-09-07

## Problem (owner's words)

"сделать per-project mcp как в claude code; настройка через desktop/ui/конфиг/
+ аналог /path/to/project/.claude папочки"

Hermes has global MCP config only. Claude Code has project-scoped MCP: a
.mcp.json / .claude folder in the project root defines servers that apply when
working in that project.

## INCIDENT (owner correction, 2026-09-07)

v1 shipped project_mcp_call as the call path and manual project_mcp_sync as
the load path. Owner: "нет, так не пойдет - просто добавить mcp с названием
project mcp; нужно чтобы сама сущность сконфигурированного mcp жила либо
per-project либо глобально и агент честно видел все видные в его скоупе mcp
и мог честно их вызвать, а не этот костыль".

Verdict: the WRAPPER is the crutch. Project servers must be NATIVE servers:
tools appear as mcp__<server>__<tool> in the model-facing tool list and are
called directly. The plugin is a loader + scoper + config manager, never a
call proxy.

## Proposed outcome (v2)

- `<project>/.hermes/mcp.json` (+ Claude compat files) loaded automatically:
  on session start and lazily before tool calls (cheap stat check; full sync
  only when the project config actually changed or the project switched).
- Sync feeds servers into the NATIVE pipeline (register_mcp_servers); tools
  become native tools; trust/breaker/keepalive all native.
- Scoping: the current project's servers replace the previous project's
  (ledger swap per profile). Global config servers always stay.
- Management surface (chat = the desktop surface): project_mcp_add/remove/
  status/sync. add/remove write .hermes/mcp.json and auto-sync.
- project_mcp_call: REMOVED in v2.

## Constraints

- No gateway restart to change a project's servers.
- Session-start sync is synchronous but only when a project config exists and
  changed (zero cost otherwise); per-server connect capped at 8s.
- Plain ASCII. No comments in source.

## Progress checklist

- [x] intent written
- [x] audit live /opt/hermes
- [x] spec v1 -> INCIDENT -> v2
- [x] plan
- [x] v1 build + e2e (wrapper path - rejected by owner)
- [ ] v2: hooks (on_session_start + pre_tool_call), drop wrapper
- [ ] v2 unit smoke
- [ ] v2 push, install update, gateway restart
- [ ] v2 e2e: fresh project, NO manual sync, direct mcp__ call works

## v2 closure (2026-09-07)

- [x] v2: hooks (on_session_start + pre_tool_call), no call proxy
- [x] v2 unit smoke: 9/9 scenarios green (test-project-mcp-v2.py)
- [x] v2 pushed (0.2.0), installed copy = origin/main, doctor clean
      (4 tools, 2 hooks, no warnings), gateway restarted (PID 129000)
- [x] v2 e2e: fresh project proj3, NO manual sync call, agent directly
      called mcp__project-echo__echo -> "echo: v2-native-auto".
      Native-first semantics confirmed live.
