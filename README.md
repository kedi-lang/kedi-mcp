# Kedi MCP Server

This directory contains the standalone Model Context Protocol (MCP) server for Kedi.

## Overview

The MCP server exposes Kedi's DSL runtime functionality as MCP tools, enabling TypeScript and other languages to interact with Kedi via the standardized MCP protocol.

## Running the Server

### Direct Execution

```bash
# From the project root
python3 kedi_mcp/server.py
```

### As Module

```bash
# From the project root
python3 -m kedi_mcp.server
```

## Available Tools

The server exposes the following MCP tools:

### `parse_kedi(source: str) -> str`

Parse Kedi DSL source code into an AST representation.

**Arguments:**

- `source`: Kedi source code to parse

**Returns:** JSON string containing AST information

### `execute_kedi(...) -> str`

Execute a Kedi program with full pipeline (parse, compile, codegen, execute).

**Arguments:**

- `source`: Kedi source code to execute
- `adapter`: Backend adapter ("pydantic" or "dspy", default: "pydantic")
- `model`: Model for template adapter (default: "groq:qwen/qwen3-32b")
- `use_codegen`: Enable AI code generation (default: true)
- `codegen_agent`: Agent for codegen ("pydantic_ai" or "mock", default: "pydantic_ai")
- `codegen_model`: Model for codegen (default: "openai:gpt-4o")
- `codegen_retries`: Number of retry stages (default: 5)
- `use_cache`: Enable codegen cache (default: true)

**Returns:** Execution output with exit code

### `test_kedi(source: str, model: str) -> str`

Run tests defined with @test: blocks.

**Arguments:**

- `source`: Kedi source code containing @test: blocks
- `model`: Model for template execution (default: "groq:qwen/qwen3-32b")

**Returns:** Test results with exit code

### `eval_kedi(source: str, model: str) -> str`

Run evaluations defined with @eval: blocks.

**Arguments:**

- `source`: Kedi source code containing @eval: blocks
- `model`: Model for template execution (default: "groq:qwen/qwen3-32b")

**Returns:** Evaluation results with exit code

### `compile_kedi(source: str, adapter: str, model: str) -> str`

Compile a Kedi program without execution.

**Arguments:**

- `source`: Kedi source code to compile
- `adapter`: Backend adapter (default: "pydantic")
- `model`: Model for adapter (default: "groq:qwen/qwen3-32b")

**Returns:** Success message or error

## Architecture

```
┌─────────────────┐
│  MCP Client     │  (TypeScript SDK, etc.)
│  (kedi.js)      │
└────────┬────────┘
         │ MCP Protocol (stdio)
         ↓
┌─────────────────┐
│  kedi_mcp/server.py  │
│  (FastMCP)      │
│                 │
│  Tools:         │
│  • parse_kedi   │
│  • execute_kedi │
│  • test_kedi    │
│  • eval_kedi    │
│  • compile_kedi │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Kedi Runtime   │
│  (src/kedi/)    │
│                 │
│  • Parser       │
│  • Compiler     │
│  • Runtime      │
│  • Adapters     │
│  • Codegen      │
└─────────────────┘
```

## Dependencies

- Python >= 3.10
- fastmcp
- kedi (with all dependencies)

## Development

### Testing the Server

You can test the server using the MCP Inspector or any MCP client:

```bash
# Start the server
python mcp/server.py

# In another terminal, use MCP client to test
```

## Configuration

The server respects Kedi environment variables:

- `KEDI_ADAPTER` - Default adapter
- `KEDI_ADAPTER_MODEL` or `MODEL_NAME` - Default model
- `KEDI_CODEGEN_AGENT` - Codegen agent
- `KEDI_CODEGEN_MODEL` - Codegen model
- `KEDI_CODEGEN_RETRIES` - Codegen retry count

## Troubleshooting

### Server Won't Start

Check that all dependencies are installed:

```bash
pip install fastmcp kedi
```

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
