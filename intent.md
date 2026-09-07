# intent: hermes-project-mcp plugin

Author: Hermes fork session
Status: in-progress
Date: 2026-09-07

## Problem (owner's words)

"сделать per-project mcp как в claude code; настройка через desktop/ui/конфиг/+
аналог /path/to/project/.claude папочки"

Hermes has global MCP config only. Claude Code has project-scoped MCP: a
.mcp.json / .claude folder in the project root defines servers that apply when
working in that project. Hermes sessions work on projects (cwd) but cannot get
project-specific MCP servers.

## Proposed outcome

A native Hermes plugin (DadaDevelopment/hermes-project-mcp) that gives every
Hermes session per-project MCP servers:

- Project config file: `<project>/.hermes/mcp.json` (native format) AND reads
  Claude Code's own `.mcp.json` / `.claude/settings.json` (mcpServers key) for
  compat - projects already configured for Claude Code work with zero edits.
- Stable tool surface (gateway/proxy pattern): `project_mcp_list`,
  `project_mcp_tools`, `project_mcp_call`, `project_mcp_add`,
  `project_mcp_remove` - the agent manages servers through chat.
- Server connections are spawned on demand (stdio/http), cached per session.
- Trust gating: servers from a project file are not callable until approved
  (approval keyed by project path + config hash), mirroring Claude Code's
  "trust this project's .mcp.json?" prompt. Approval via explicit tool call.
- Global config surface: allowlist/denylist + defaults in config.yaml
  (plugins.entries.project-mcp.settings.*).

## Affected systems

- New repo DadaDevelopment/hermes-project-mcp (push approved pattern from
  share-artifact precedent: "выложим на gh DadaDevelopment").
- This Hermes instance: install + enable plugin, gateway restart (established
  pattern, done twice before).
- No new public endpoints. No runtime external pushes. Server processes are
  spawned locally per project config.

## Constraints

- Handlers must discover the session's project root (cwd chain) at call time.
- No gateway restart needed to change a project's servers (that is the point).
- Plain ASCII. No comments in source. Docstrings allowed.

## Open questions

- Desktop UI panel: v2. v1 = chat-driven management via tools + project file +
  global config. Owner listed "desktop/ui" as a config surface; tools driven
  from the chat ARE the desktop surface today (agent edits config on request).

## Progress checklist

- [x] intent written
- [ ] audit live /opt/hermes: MCP config shape, handler kwargs/session cwd,
      call_mcp internals, desktop plugin API
- [ ] spec: config file formats + tool schemas + trust model
- [ ] plan: modules, failure modes
- [x] build + local tests (offline loader-repro: register OK, handler call OK
      after relative-import fix; before fix the exact ModuleNotFoundError
      'config_source' reproduced)
- [x] push (79eeb7b, main) + installed copy /opt/data/plugins/project-mcp synced
- [x] live dogfood e2e (2026-09-07, proj2): project_mcp_add wrote
      .hermes/mcp.json, sync connected echo2 with 2 tools, project_mcp_call
      echo round-trip returned "echo: ping-from-e2e"
- [ ] hermes plugins doctor + gateway restart: pending. NOTE: the gateway
      process still holds pre-fix plugin code in memory; fresh CLI processes
      (hermes -z) get the fix immediately, gateway-served sessions keep hitting
      ModuleNotFoundError until the gateway restarts.

## Incident (2026-09-07, found via live e2e attempt)

All five project_mcp_* tools were dead on call: handlers used absolute sibling
imports (`from config_source import ...`, `import syncer`) inside function
bodies, but plugins_loader imports directory plugins as `hermes_plugins.<slug>`
with explicit __path__ and never puts the plugin dir on sys.path. Tool
registration succeeded, so the plugin looked healthy until the first call.
Fix: relative imports (`from .config_source import ...`, `from . import
syncer`) in __init__.py and syncer.py, commit 79eeb7b. Lesson: a plugin that
only registers is not a plugin that works - the loader-repro (import via
hermes_plugins package path, then CALL a handler) belongs in the build stage,
not after install.
