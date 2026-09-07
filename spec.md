# spec: hermes-project-mcp

Author: Hermes fork session
Status: accepted
Date: 2026-09-07

## Goal

Per-project MCP servers for Hermes, semantics 1:1 with Claude Code:
a config file inside the project defines MCP servers that apply to sessions
working in that project. Zero global config edits, zero gateway restarts.

## Ground truth from /opt/hermes audit

- `agent.runtime_cwd.resolve_agent_cwd()` - the session's cwd (ContextVar >
  scoped TERMINAL_CWD > launch dir). "The project" = this path's git root if
  any, else the path itself.
- `tools.mcp_tool_discovery.register_mcp_servers({name: cfg})` - public entry
  into the NATIVE MCP pipeline: security filter, connect (stdio/http), tool
  discovery, registry registration as `mcp__<server>__<tool>` in toolset
  `mcp-<server>`, trust metadata, schema cache. Idempotent per name.
- `MCPServerTask.shutdown()` deregisters the server's tools (idempotent).
- Server config supports `cwd` for stdio children (transport spawn passes
  `config.get("cwd")`).
- `trust: untrusted` on a server config gives the call-time approval gate for
  write-capable tools (Claude Code's "trust this project's servers?" analog).
- Hooks available to plugins: `on_session_start` (once per new session,
  kwargs: session_id/model/platform) and `pre_tool_call` (kwargs: tool_name,
  args, session_id, ...). `pre_tool_call` may return None to proceed.
- Plugin tools registered via `ctx.register_tool` get `parent_agent` kwarg
  when dispatched through PluginContext.dispatch_tool.
- Registry: `registry.get_toolset_for_tool`, `registry.deregister`,
  `registry.snapshot`; `tools.mcp_tool._core._mcp_tool_server_names` maps
  mcp tool name -> server name.
- `_core` lives at `tools.mcp_tool_common._core` (an origin proxy onto
  `tools.mcp_tool` module state).
- `_load_mcp_config()` (global) does NOT read any project files today.
- `hermes_cli.mcp_security.validate_mcp_server_entry(name, entry)` - the
  exfiltration/persistence shape filter used on every server entry.
- `tools.mcp_tool_config._interpolate_env_vars(cfg)` - ${VAR} interpolation
  used by the native loader; reuse it so project configs behave identically.
- No core support for project files exists today (grep for .mcp.json/.claude
  in mcp modules: zero hits).

## Config files (in priority order, merged shallow per server name)

1. `<project>/.hermes/mcp.json` - native format:
   `{"mcpServers": {name: {command, args, env, cwd?, trust?, lazy?, enabled?,
   tools?: {include[], exclude[]}, url?, headers?}}}`. The `mcpServers` key
   mirrors Claude Code; a bare top-level object of servers is also accepted.
2. `<project>/.mcp.json` - Claude Code's own file, same `mcpServers` shape.
3. `<project>/.claude/settings.json` and `.claude/settings.local.json` -
   `mcpServers` key read for compat. local overrides shared per Claude CC.

Merge order (later wins per server name): .claude/settings.json <
.claude/settings.local.json < .mcp.json < .hermes/mcp.json.

Server name collision handling: a project server keeps its native-style tool
namespace `mcp__<server>__<tool>`; if a GLOBAL server of the same name is
already connected, the project one is skipped and the conflict is reported by
the status tool (never silently shadow a global server; never kill a global
server's tools).

Path safety: `cwd` inside a project server config may use `${project}` -
expanded to the project root before interpolation. Relative `cwd` values are
resolved against the project root. This lets a repo ship e.g.
`cwd: "${project}/server"`.

## Tools (v2: native-first, no call proxy)

- `project_mcp_sync()` - rescan current project, connect new/changed servers
  (register_mcp_servers), disconnect removed/stale ones (shutdown), return
  per-server status. Idempotent; safe to call any time. ALSO auto-invoked:
  (a) once on session start when the project has a config,
  (b) lazily from a `pre_tool_call` hook when a tool is about to run and the
  project config changed since the last sync (stat-mtime guard, then cheap
  hash; connect only on real change). The model-facing tools after sync are
  the native `mcp__<server>__<tool>` - the agent calls them directly.
- `project_mcp_status()` - report project root, config files found, per-server
  state (connected/failed/disabled), conflict notes. Read-only.
- `project_mcp_add(name, command|url, args?, env?, trust?, cwd?)` - write an
  entry into `<project>/.hermes/mcp.json` (creating dirs), then sync; the new
  native tools are usable from the NEXT turn (current turn's tool list is
  frozen - say so in the result).
- `project_mcp_remove(name)` - delete entry from project config, then sync.

## Scoping (per-project or global, never both for one name)

- Servers loaded from the project live in the same native namespace as
  global ones. On project switch, the plugin disconnects exactly the servers
  it loaded for the previous project (its own ledger), never global servers.
- Global config always wins a name collision (native rule, kept).

## Trust model (Claude Code parity)

- Native gate does the heavy lifting: `trust: untrusted` in a server config
  makes write-capable tools prompt the user at call time (Claude Code's
  "trust this project's servers?" analog, per-call instead of once).
- Native default when `trust` is absent is FULL (matches global config
  semantics; a project file is written by the user, same trust as
  config.yaml). The SKILL tells the agent to recommend `trust: untrusted`
  for third-party configs.
- Per-project approval memory: after a project's config file set changes
  (content hash), the plugin marks the project "unconfirmed". The first
  `project_mcp_sync` after a change returns a `confirmation_required` notice
  listing what changed; tools are still connected but the summary tells the
  agent to surface it. This mirrors CC's "new servers in .mcp.json - review"
  without a hard UI modal.
- Global opt-out: `plugins.entries.project-mcp.settings.disabled_projects`
  (list of project root paths) and `enabled: false` kill-switch in settings.

## Failure modes

- No project file -> tools report "no project MCP config" (never an error).
- Bad JSON -> sync reports the parse error, touches nothing.
- Suspicious entries (IOC/egress/persistence) -> dropped by the native filter;
  sync reports them as rejected.
- Server fails to connect -> sync reports failed + error string; other servers
  proceed.
- Project deleted mid-session -> cwd resolver falls back per core; sync is a
  no-op reporting "no project".

## Non-goals (v1)

- Desktop UI panel (tools ARE the chat surface; agent edits config on request).
- Per-session tool allowlists beyond native `tools.include/exclude`.

## Progress

- [x] audit
- [x] spec
- [ ] plan
- [ ] build + unit smoke
- [ ] install, doctor, gateway restart
- [ ] live e2e in a real project dir
