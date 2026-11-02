# TouchDesigner MCP bridge

A general-purpose [Model Context Protocol](https://modelcontextprotocol.io) server for a live TouchDesigner session. Any stdio MCP client can execute TD Python, inspect and connect operators, read errors, capture TOP output, analyze image channels, and checkpoint components.

```
MCP client --stdio--> Node server --HTTP--> TD WebServer DAT
```

No creative project, AI provider account, controller, or workflow service is required. The TD component embeds its callbacks and can be copied/exported into other projects without a path back to this repository.

## Requirements

- Node.js 20 or newer and npm, on the MCP host.
- TouchDesigner with Python and a WebServer DAT, on the same machine by default.
- A trusted local connection. The HTTP bridge executes Python with TD's permissions and has no authentication. Restrict WebServer binding/firewall access to trusted clients; do not expose its port publicly.

## Install the TD component

Preserve your current project first. Run this in the TouchDesigner Textport, replacing the source path with your checkout:

```python
installer = '/absolute/path/to/TD_MCP/touchdesigner/install_bridge.py'
ns = {'__file__': installer}
exec(compile(open(installer, encoding='utf-8').read(), installer, 'exec'), ns)
bridge = ns['install_bridge'](op('/project1'), name='TD_MCP', port=9980)
```

The installer refuses an existing name and creates an **inactive** Base COMP containing `webserver`, `webserver_callbacks`, `error1`, and a README DAT. It embeds callback source rather than using an external File In DAT. Parent path/name are configurable. Inspect it, save to a new project path, then manually activate `webserver`. Use only one active bridge on a given port. Never restart a serving bridge through its own MCP connection.

Alternatively, create those DATs in any COMP, paste `touchdesigner/webserver_callbacks.py` into the Text DAT, and set the WebServer's Callbacks DAT to that sibling. Keep the Error DAT named `error1`. No `.toe` or `.tox` download is needed. You may export the COMP locally as a `.tox`; binaries are intentionally ignored.

## Install and register the MCP server

```sh
cd td-mcp-server
npm ci
npm start
```

`npm start` speaks MCP over stdio; normally your MCP client launches it. Copy the `touchdesigner` entry from [mcp.example.json](mcp.example.json) into your host's configuration and replace the absolute source path. Host-specific `.mcp.json` and `mcp_config.json` are local and ignored. The server resolves its bundled API database relative to its source, independently of the launch directory.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TD_HOST` | `127.0.0.1` | TD HTTP bridge host |
| `TD_PORT` | `9980` | WebServer DAT port |
| `TD_TIMEOUT_MS` | `30000` | HTTP request timeout; timeout does not cancel TD execution |
| `TD_API_DB` | bundled `td_python_api.json` | Optional Python API snapshot override |
| `TD_CHECKPOINTS_DIR` | repo `checkpoints/` | Checkpoint index and snapshots; must be accessible at the same path on both machines |
| `TD_TONE_RULES` | bundled `tone-rules.json` | Optional custom rules JSON; use an ignored local copy for edits |

## Tools and endpoints

- Scripts: `execute_script`, `validate_script`, `get_errors`.
- Networks: `create_operator`, `delete_operator`, `connect_operators`, `disconnect_operators`, `get_operator_info`, `list_operators`, `get_par_value`, `set_par_value`.
- Images: `take_screenshot`, `analyze_image_tone`, `set_tone_rule`, `list_tone_rules`. Tone rules are advisory labels and require explicitly supplied analysis CHOPs; no fixed network is expected.
- Recovery: `save_checkpoint`, `restore_checkpoint`, `list_checkpoints`, `delete_checkpoint`. Restore replaces the target operator; checkpoint names may replace previous entries. Preserve unique names when prior snapshots matter.
- Resources: `td://api/classes`, `td://api/class/{name}`. Snapshot validation is advisory; check the running TD build for authoritative API behavior.

HTTP endpoints: `GET /health`, `/errors`, `/operator?path=...`, `/chop?path=...`, `/screenshot?path=...`, `/image_stats?rows_chop=...&cols_chop=...`; `POST /execute` accepts `script` and optional `undo_label`.

Start with `/health` and `list_operators` at your actual network root. Screenshots default to `/project1/out1` for compatibility; supply your TOP path if different. PNGs default to the TD machine's temporary `td-mcp/screenshots` directory; `save_dir` explicitly selects a durable destination. TOP capture cannot capture arbitrary panel UI.

## Safe editing and recovery

Changes affect the live session immediately. Preserve a new unused project save or scoped checkpoint before editing; verify errors, operator/parameter state, and relevant TOP output; then save another version. Verify `project.name` and actual saved filename because TD can increment requested suffixes. Undo blocks do not guarantee rollback of file writes or all TD operations. On timeouts, inspect state before retrying.

Read [AGENTS.md](AGENTS.md), [session learnings](docs/SESSION_LEARNINGS.md), and the [agent skill](.agents/skills/td-mcp/SKILL.md). They preserve lessons from prior work without requiring those projects.

## Development and repository scope

```sh
cd td-mcp-server
npm test
```

```sh
python -m unittest discover -s tests -p "test_*.py"
```

Tracked: Node MCP bridge, source installer/callbacks, API snapshots and optional scrapers, generic setup, tests, reusable agent guidance, and npm lockfile. Scrapers optionally require `requests` and `beautifulsoup4`.

Ignored: TD project/component binaries, backups, runtime checkpoint indexes, render/review outputs, host settings/hooks, and local creative pipelines. Existing local work is preserved on disk. Ignoring/untracking files does not remove them from old Git commits; no history rewrite is performed.
