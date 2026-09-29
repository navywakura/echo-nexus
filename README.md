# echo-nexus

**The official terminal harness for ECHO.** Dark purple, black and white.
Developer: **rxlabs** · © 2026 RxLabs · Harness source: **MIT**.

[Website](https://www.rxlabs.org/echo-nexus) · [Guía en español](https://www.rxlabs.org/docs/echoai/echo-nexus)

```sh
curl -fsSL https://rxlabs.org/echo-nexus.sh | bash
echo-nexus
```

Linux and macOS, Python 3.10+, curl, and a UTF-8 terminal. Windows: use WSL.
No sudo. The installer creates a private virtual environment, checks the
published wheel's SHA-256, and keeps a timestamped installation log. Add
`~/.local/bin` to PATH if your shell does not already include it.
The exact installer is available at `scripts/install.sh`; inspect it before
running if preferred. Python dependencies are downloaded from PyPI.

## First session

```text
/help
/agents
/demo
/devtest list
/devtest
```

Tab completes commands and test IDs; inline help describes syntax. F2 expands
the telemetry/image panels on small terminals. `/stars off` disables motion.
`/stop` stops the development process owned by the harness; it does not stop
independent experiments. Remote API processing may finish after cancellation.

**The engine is a separate installation.** This repository contains the TUI,
connectors, image renderer, installer, protocol documentation and harness tests.
It contains no ECHO policies, weights, training data, exam inputs or core source.
If `echoai` is on PATH, the harness exposes its public `info`, `situate`, `life`
and `resume` commands. Research installations supply an operator-owned backend
manifest with their supported development tests.

```text
/backend /absolute/path/backend.json
/devtest list
/devtest all
/watch /absolute/path/thought.jsonl
/image /absolute/path/frame.png
```

`/devtest` runs the backend's default development set. `all` runs all declared
development tests sequentially, stopping on error. Evidence entries display
existing reports. Sealed entries cannot be executed by the runner. `/demo` is
a labeled synthetic viewer fixture; it is not ECHO and earns no ARC score.

## Optional neocortex

Export the provider's key in your shell, then launch echo-nexus. Supply the
**environment variable name**, never the secret itself, in the command:

```text
/connect api https://provider.example/v1 your-model PROVIDER_API_KEY
/connect anthropic https://api.anthropic.com/v1 your-model ANTHROPIC_API_KEY
/connect local /absolute/path/model.gguf
/disconnect
```

The API must implement Chat Completions or Anthropic Messages. Local GGUF
requires `llama-server` on PATH. It binds to loopback, uses four CPU threads,
and writes its own log. Models are never downloaded automatically.
Connection configuration is validated immediately; credentials and remote model
availability are checked on the first message. The harness keeps conversation
context in memory and writes redacted session logs with user-only permissions.
Chat sends only the text you enter and recent conversation, not your local
telemetry, files or images. Treat session logs as personal data.

The neocortex is a language interface. Its text is labeled as a **proposal**;
it cannot operate motors, execute code, invoke tools or update ECHO facts.
This does not enable the NEXUS-0 core's optional cortex.

## MCP and installed agents

`/agents` and installation detection only find executable paths. They never
start coding agents or alter their configuration. Connect a trusted MCP stdio
server explicitly, then inspect and call its tools:

```text
/mcp connect echo -- echoai mcp --root /absolute/project
/mcp connect claude -- claude mcp serve
/mcp tools echo
/mcp call echo echo_receipts {"limit":5}
/mcp close echo
```

MCP tools execute with the connected server's permissions; a tool can modify
files. Only explicit `/mcp call` commands invoke tools. The neocortex cannot
invoke them. Stdio protocol versions are negotiated. Streamable HTTP MCP is
not included in 0.1.0. Current Codex installations may expose app-server
instead of the retired MCP server: detection does not claim these protocols
are interchangeable. Supply a compatible MCP adapter if needed.

## What the visualization means

The tree shows fields received from ECHO: observations, CAM/Q/T, gate verdicts
and actions. LIF/Adaptive-LIF counts are shown only when a backend emits actual
monitor samples. This monitor is distinct from the policy controlling ECHO.
Missing measurements stay **sin muestra**; chat calls never fabricate neuron
activity. Stars are decoration. JSONL files are read-only inputs; the harness
log is an operator log, not a second thought bus.

Grids and PNG/JPEG images render as true-color half blocks, including in SSH.
Large images are downsampled to the panel. This is a terminal view, not a
pixel-perfect image editor. `--capture PATH.svg` captures the actual TUI widgets.
Backend development runs can stream frame events for live ARC and custom worlds.

## Develop and verify

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
echo-nexus --capture session.svg --command /demo
```

See [the backend contract](docs/backend.md). Custom manifests are executable
operator configuration: do not load one from an untrusted project. The harness
runs argv directly, never through a shell, and does not import ECHO source.
Process exit zero means the command finished successfully; it does not turn a
scientific milestone green. Research audits decide that independently.

## License and scope

MIT covers this harness. ECHO core and model licenses remain separate.
Brand names are reserved; see [NOTICE](NOTICE). The new echo-nexus name makes
no claim of registered trademark status.

## Protocol references

- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Textual testing and screenshots](https://textual.textualize.io/guide/testing/)
- [OpenAI's archived Codex MCP integration and migration note](https://developers.openai.com/cookbook/examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk)
