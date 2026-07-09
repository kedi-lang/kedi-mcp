# kedi-mcp

`kedi-mcp` exposes stable Kedi core workflows through a FastMCP server.

## Install

From the repository root:

```bash
./kedi-mcp/install.sh
```

The installer uses `uv` if available. If `uv` is missing, it installs `uv` with the
official installer, then installs both `kedi` and `kedi-mcp` as user-level tool
entries.

## Run

```bash
kedi-mcp
```

By default the server runs over stdio for MCP clients.

## Tools

- `kedi_health`: report server readiness and executable discovery.
- `kedi_parse`: parse source text or a `.kedi` file and return a stable program summary.
- `kedi_compile`: parse and compile source without constructing an LLM adapter.
- `kedi_schema`: return JSON schemas for Kedi procedures.
- `kedi_run`: run source text or a file path.
- `kedi_test`: run `@test` blocks from a `.kedi` file.
- `kedi_eval`: run `@eval` blocks from a `.kedi` file.

Tool names intentionally use underscores for broad MCP client compatibility.
