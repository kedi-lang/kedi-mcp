# kedi-mcp

`kedi-mcp` exposes stable Kedi core workflows through a FastMCP server.

## Install

From a Kedi workspace with this repository checked out as `kedi-mcp/`:

```bash
./kedi-mcp/install.sh
```

The installer uses `uv` if available. If `uv` is missing, it installs `uv` with the
official installer, then installs both `kedi` and `kedi-mcp` as user-level tool
entries.

For a standalone clone of this repository, point the installer at a compatible
Kedi source checkout instead of its default parent directory:

```bash
KEDI_INSTALL_SPEC=/path/to/kedi ./install.sh
```

Requires Python 3.10+ and Kedi `>=0.4,<0.5`. The installer creates user-level
tool environments; it does not install into the currently activated virtual
environment.

## Run

```bash
kedi-mcp
```

By default the server runs over stdio for MCP clients.

```json
{
  "mcpServers": {
    "kedi": {
      "command": "kedi-mcp"
    }
  }
}
```

Use the executable's absolute path if the client does not inherit your shell's
`PATH`. Run it only for trusted clients: execution tools can run embedded
Python and use the server process's filesystem access and credentials. This
server is not a sandbox.

## Tools

- `kedi_health`: report server readiness and executable discovery.
- `kedi_parse`: parse source text or a `.kedi` file and return a stable program summary.
- `kedi_compile`: parse and compile source without constructing an LLM adapter.
- `kedi_schema`: return JSON schemas for Kedi procedures.
- `kedi_run`: run source text or a file path.
- `kedi_test`: run `@test` blocks from a `.kedi` file.
- `kedi_eval`: run `@eval` blocks from a `.kedi` file.

Tool names intentionally use underscores for broad MCP client compatibility.
