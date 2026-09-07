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
- [ ] build + local tests
- [ ] push, install, doctor, gateway restart
- [ ] live dogfood e2e (real project dir, real stdio server)
