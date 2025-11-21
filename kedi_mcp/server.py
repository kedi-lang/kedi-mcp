"""MCP Server for Kedi SDK.

This module provides a standalone Model Context Protocol (MCP) server that exposes
Kedi's parse, compile, and execution infrastructure as MCP tools.

TypeScript (and other) clients can connect to this server via the MCP SDK.

Usage:
    python kedi_mcp/server.py

    python -m kedi_mcp.server
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path

from fastmcp import FastMCP

from kedi.agent_adapter.adapters import DSPyAdapter, PydanticAdapter
from kedi.app import maybe_run_codegen, run_evals_cli, run_program_cli, run_tests_cli
from kedi.lang import compile_program, parse_program

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

mcp = FastMCP("kedi-sdk")


@mcp.tool()
def parse_kedi(source: str) -> str:
    """Parse Kedi DSL source code into an AST representation.

    Args:
        source: Kedi source code to parse

    Returns:
        JSON string containing AST information
    """

    try:
        program = parse_program(source)

        ast_info = {
            "procedures": [
                {
                    "name": p.name,
                    "params": p.params,
                    "param_types": p.param_type_annotations,
                    "return_type": p.return_type_annotation,
                    "has_ai_prompt": bool(getattr(p, "ai_prompt", None)),
                    "ai_prompt": getattr(p, "ai_prompt", None),
                }
                for p in program.procedures
            ],
            "type_defs": [
                {
                    "name": td.name,
                    "fields": td.fields,
                    "field_types": td.field_type_annotations,
                }
                for td in program.type_defs
            ],
            "has_toplevel_return": program.toplevel_return is not None,
            "has_prelude": program.prelude is not None,
        }

        return json.dumps(ast_info, indent=2)
    except Exception as e:
        return f"Parse error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"


@mcp.tool()
def execute_kedi(
    source: str,
    adapter: str = "pydantic",
    model: str = "groq:qwen/qwen3-32b",
    use_codegen: bool = True,
    codegen_agent: str = "pydantic_ai",
    codegen_model: str = "openai:gpt-4o",
    codegen_retries: int = 5,
    use_cache: bool = True,
) -> str:
    """Execute a Kedi program with full pipeline (parse, compile, codegen, execute).

    Args:
        source: Kedi source code to execute
        adapter: Backend adapter for template execution (pydantic or dspy)
        model: Model for template adapter
        use_codegen: Enable AI code generation for AI-prompted procedures
        codegen_agent: Agent for AI code generation
        codegen_model: Model for codegen agent
        codegen_retries: Number of retry stages for codegen
        use_cache: Enable reading/writing codegen cache

    Returns:
        Execution output as string
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".kedi", delete=False, encoding="utf-8") as f:
        f.write(source)
        temp_path_str = f.name

    try:
        if use_codegen:
            ok, err = maybe_run_codegen(
                temp_path_str,
                agent=codegen_agent,
                model=codegen_model,
                retries=codegen_retries,
                use_cache=use_cache,
            )
            if not ok:
                return f"Codegen failed: {err or 'Code generation failed'}"

        # Execute program
        exit_code, output = run_program_cli(
            temp_path_str, adapter=adapter, model=model
        )

        return f"Exit code: {exit_code}\n\nOutput:\n{output}"
    except Exception as e:
        return f"Execution error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
    finally:
        # Cleanup
        Path(temp_path_str).unlink(missing_ok=True)
        if not use_cache:
            cache_path = Path(temp_path_str).with_suffix(".cache.kedi")
            cache_path.unlink(missing_ok=True)


@mcp.tool()
def test_kedi(source: str, model: str = "groq:qwen/qwen3-32b") -> str:
    """Run tests defined with @test: blocks in a Kedi program.

    Args:
        source: Kedi source code containing @test: blocks
        model: Model for template execution

    Returns:
        Test results as string
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".kedi", delete=False, encoding="utf-8") as f:
        f.write(source)
        temp_path_str = f.name

    try:
        exit_code, output = run_tests_cli(temp_path_str, model=model)

        return f"Exit code: {exit_code}\n\n{output}"
    except Exception as e:
        return f"Test error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
    finally:
        Path(temp_path_str).unlink(missing_ok=True)
        cache_path = Path(temp_path_str).with_suffix(".cache.kedi")
        cache_path.unlink(missing_ok=True)


@mcp.tool()
def eval_kedi(source: str, model: str = "groq:qwen/qwen3-32b") -> str:
    """Run evaluations defined with @eval: blocks in a Kedi program.

    Args:
        source: Kedi source code containing @eval: blocks
        model: Model for template execution

    Returns:
        Evaluation results as string
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".kedi", delete=False, encoding="utf-8") as f:
        f.write(source)
        temp_path_str = f.name

    try:
        exit_code, output = run_evals_cli(temp_path_str, model=model)

        return f"Exit code: {exit_code}\n\n{output}"
    except Exception as e:
        return f"Eval error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
    finally:
        Path(temp_path_str).unlink(missing_ok=True)
        cache_path = Path(temp_path_str).with_suffix(".cache.kedi")
        cache_path.unlink(missing_ok=True)


@mcp.tool()
def compile_kedi(source: str, adapter: str = "pydantic", model: str = "groq:qwen/qwen3-32b") -> str:
    """Compile a Kedi program (parse + compile, no execution).

    Args:
        source: Kedi source code to compile
        adapter: Backend adapter (pydantic or dspy)
        model: Model for adapter

    Returns:
        Success message or error
    """

    try:
        program = parse_program(source)

        adapter_impl = (
            DSPyAdapter(model=model or "groq/qwen/qwen3-32b")
            if adapter == "dspy"
            else PydanticAdapter(model=model or "groq:qwen/qwen3-32b")
        )

        rt = compile_program(program, adapter=adapter_impl)

        return "Compilation successful"
    except Exception as e:
        return f"Compile error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"


def main():
    """Main entry point for Kedi MCP server."""

    try:
        mcp.run(show_banner=False)
    except Exception as e:
        print(f"Server error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
