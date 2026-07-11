from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from kedi.app import (CliArgs, run_evals_cli, run_program_cli, run_source_cli,
                      run_tests_cli)
from kedi.error_rendering import render_parse_error
from kedi.lang import (compile_program, parse_program,
                       program_procedure_json_schemas)
from kedi.lang.ast import (ModuleExport, ModuleImport, Program,
                           ProgramWithValidation, Span)
from kedi.lang.parser.diagnostics import KediDiagnostic, KediParseError
from kedi.utils import parse_args

ToolKind = Literal["health", "parse", "compile", "schema", "run", "test", "eval"]


class SpanPayload(BaseModel):
    start_byte: int
    end_byte: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    source_path: str | None = None
    source_id: str | None = None


class DiagnosticPayload(BaseModel):
    severity: str
    message: str
    code: str | None = None
    snippet: str | None = None
    span: SpanPayload | None = None


class ProgramSummary(BaseModel):
    procedures: list[str]
    imports: list[str]
    exports: list[str]
    type_defs: list[str]
    profiles: list[str]
    parser_warning_count: int
    tests: list[str] = Field(default_factory=list)
    evals: list[str] = Field(default_factory=list)


class BaseToolResult(BaseModel):
    ok: bool
    kind: ToolKind
    message: str | None = None
    diagnostics: list[DiagnosticPayload] = Field(default_factory=list)
    rendered: str | None = None


class HealthResult(BaseToolResult):
    kind: ToolKind = "health"
    python: str
    cwd: str
    kedi_executable: str | None
    kedi_mcp_executable: str | None
    fastmcp: bool


class ParseResult(BaseToolResult):
    kind: ToolKind = "parse"
    source_path: str
    program: ProgramSummary | None = None


class CompileResult(BaseToolResult):
    kind: ToolKind = "compile"
    source_path: str
    program: ProgramSummary | None = None
    schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SchemaResult(BaseToolResult):
    kind: ToolKind = "schema"
    source_path: str
    schemas: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RunResult(BaseToolResult):
    kind: ToolKind = "run"
    source_path: str
    exit_code: int
    output: str


class ValidationResult(BaseToolResult):
    source_path: str
    exit_code: int
    output: str


class TestResult(ValidationResult):
    kind: ToolKind = "test"


class EvalResult(ValidationResult):
    kind: ToolKind = "eval"


@dataclass(frozen=True)
class SourceInput:
    text: str
    source_path: str
    is_file: bool


def create_server() -> FastMCP:
    server = FastMCP("kedi-mcp")

    @server.tool(name="kedi_health")
    def kedi_health() -> dict[str, Any]:
        """Report Kedi MCP server readiness and executable discovery."""
        return HealthResult(
            ok=True,
            message="Kedi MCP server is ready.",
            diagnostics=[],
            rendered=None,
            python=sys.version.split()[0],
            cwd=os.getcwd(),
            kedi_executable=shutil.which("kedi"),
            kedi_mcp_executable=shutil.which("kedi-mcp"),
            fastmcp=True,
        ).model_dump()

    @server.tool(name="kedi_parse")
    def kedi_parse(source: str | None = None, path: str | None = None) -> dict[str, Any]:
        """Parse Kedi source and return a stable program summary."""
        loaded = _load_source(source=source, path=path)
        if isinstance(loaded, BaseToolResult):
            return ParseResult(
                ok=False,
                message=loaded.message,
                diagnostics=loaded.diagnostics,
                rendered=loaded.rendered,
                source_path="<invalid>",
            ).model_dump()
        try:
            program = parse_program(loaded.text, source_path=loaded.source_path)
        except KediParseError as error:
            return _parse_error_result(error, loaded.source_path).model_dump()
        except Exception as error:  # pragma: no cover - exercised through compile/run wrappers.
            return ParseResult(
                ok=False,
                message=str(error),
                diagnostics=[],
                rendered=str(error),
                source_path=loaded.source_path,
            ).model_dump()
        return ParseResult(
            ok=True,
            message="Parsed successfully.",
            diagnostics=_diagnostics(program.parser_warnings),
            rendered=None,
            source_path=loaded.source_path,
            program=_program_summary(program),
        ).model_dump()

    @server.tool(name="kedi_compile")
    def kedi_compile(
        source: str | None = None,
        path: str | None = None,
        include_schemas: bool = True,
    ) -> dict[str, Any]:
        """Compile Kedi source without constructing an LLM adapter."""
        result = _compile_source(source=source, path=path, include_schemas=include_schemas)
        return result.model_dump()

    @server.tool(name="kedi_schema")
    def kedi_schema(
        source: str | None = None,
        path: str | None = None,
        include_nested: bool = False,
    ) -> dict[str, Any]:
        """Return JSON schemas for Kedi procedure inputs."""
        loaded = _load_source(source=source, path=path)
        if isinstance(loaded, BaseToolResult):
            return SchemaResult(
                ok=False,
                message=loaded.message,
                diagnostics=loaded.diagnostics,
                rendered=loaded.rendered,
                source_path="<invalid>",
            ).model_dump()
        try:
            program = parse_program(loaded.text, source_path=loaded.source_path)
            runtime = compile_program(program)
            schemas = program_procedure_json_schemas(
                runtime, program, include_nested=include_nested
            )
        except KediParseError as error:
            return SchemaResult(
                ok=False,
                message="Parse failed.",
                diagnostics=_diagnostics(error.diagnostics),
                rendered=render_parse_error(error, use_color=False),
                source_path=loaded.source_path,
            ).model_dump()
        except Exception as error:
            return SchemaResult(
                ok=False,
                message=str(error),
                diagnostics=[],
                rendered=str(error),
                source_path=loaded.source_path,
            ).model_dump()
        return SchemaResult(
            ok=True,
            message="Schema generated successfully.",
            diagnostics=_diagnostics(program.parser_warnings),
            rendered=None,
            source_path=loaded.source_path,
            schemas=schemas,
        ).model_dump()

    @server.tool(name="kedi_run")
    def kedi_run(
        source: str | None = None,
        path: str | None = None,
        args: dict[str, str | int | float | bool] | None = None,
        adapter: str = "pydantic",
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run a Kedi program from source text or a file path."""
        loaded = _load_source(source=source, path=path)
        if isinstance(loaded, BaseToolResult):
            return RunResult(
                ok=False,
                message=loaded.message,
                diagnostics=loaded.diagnostics,
                rendered=loaded.rendered,
                source_path="<invalid>",
                exit_code=2,
                output="",
            ).model_dump()
        try:
            runtime_args = _runtime_args(args)
            if loaded.is_file:
                code, output = run_program_cli(
                    loaded.source_path,
                    adapter=adapter,
                    model=model,
                    runtime_args=runtime_args,
                )
            else:
                code, output = run_source_cli(
                    loaded.text,
                    adapter=adapter,
                    model=model,
                    runtime_args=runtime_args,
                    source_path=loaded.source_path,
                )
        except KediParseError as error:
            return RunResult(
                ok=False,
                message="Parse failed.",
                diagnostics=_diagnostics(error.diagnostics),
                rendered=render_parse_error(error, use_color=False),
                source_path=loaded.source_path,
                exit_code=1,
                output="",
            ).model_dump()
        except Exception as error:
            return RunResult(
                ok=False,
                message=str(error),
                diagnostics=[],
                rendered=str(error),
                source_path=loaded.source_path,
                exit_code=1,
                output="",
            ).model_dump()
        return RunResult(
            ok=code == 0,
            message=None if code == 0 else "Kedi program failed.",
            diagnostics=[],
            rendered=None,
            source_path=loaded.source_path,
            exit_code=code,
            output=output,
        ).model_dump()

    @server.tool(name="kedi_test")
    def kedi_test(
        path: str,
        adapter: str = "pydantic",
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run @test blocks from a Kedi file."""
        source_path = _resolve_existing_file(path)
        if source_path is None:
            return TestResult(
                ok=False,
                message=f"Kedi source file does not exist: {path}",
                diagnostics=[],
                rendered=None,
                source_path=path,
                exit_code=2,
                output="",
            ).model_dump()
        try:
            code, output = run_tests_cli(str(source_path), adapter=adapter, model=model)
        except Exception as error:
            return TestResult(
                ok=False,
                message=str(error),
                diagnostics=[],
                rendered=str(error),
                source_path=str(source_path),
                exit_code=1,
                output="",
            ).model_dump()
        return TestResult(
            ok=code == 0,
            message=None if code == 0 else "Kedi tests failed.",
            diagnostics=[],
            rendered=None,
            source_path=str(source_path),
            exit_code=code,
            output=output,
        ).model_dump()

    @server.tool(name="kedi_eval")
    def kedi_eval(
        path: str,
        adapter: str = "pydantic",
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run @eval blocks from a Kedi file."""
        source_path = _resolve_existing_file(path)
        if source_path is None:
            return EvalResult(
                ok=False,
                message=f"Kedi source file does not exist: {path}",
                diagnostics=[],
                rendered=None,
                source_path=path,
                exit_code=2,
                output="",
            ).model_dump()
        try:
            code, output = run_evals_cli(str(source_path), adapter=adapter, adapter_model=model)
        except Exception as error:
            return EvalResult(
                ok=False,
                message=str(error),
                diagnostics=[],
                rendered=str(error),
                source_path=str(source_path),
                exit_code=1,
                output="",
            ).model_dump()
        return EvalResult(
            ok=code == 0,
            message=None if code == 0 else "Kedi evals failed.",
            diagnostics=[],
            rendered=None,
            source_path=str(source_path),
            exit_code=code,
            output=output,
        ).model_dump()

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Kedi FastMCP server.")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=("stdio", "sse", "streamable-http"),
        help="FastMCP transport to run. Defaults to stdio.",
    )
    parser.add_argument("--host", default=None, help="Host for HTTP transports.")
    parser.add_argument("--port", default=None, type=int, help="Port for HTTP transports.")
    args = parser.parse_args(argv)

    kwargs: dict[str, Any] = {}
    if args.host is not None:
        kwargs["host"] = args.host
    if args.port is not None:
        kwargs["port"] = args.port

    create_server().run(transport=args.transport, **kwargs)


def _compile_source(
    *,
    source: str | None,
    path: str | None,
    include_schemas: bool,
) -> CompileResult:
    loaded = _load_source(source=source, path=path)
    if isinstance(loaded, BaseToolResult):
        return CompileResult(
            ok=False,
            message=loaded.message,
            diagnostics=loaded.diagnostics,
            rendered=loaded.rendered,
            source_path="<invalid>",
        )
    try:
        program = parse_program(loaded.text, source_path=loaded.source_path)
        runtime = compile_program(program)
        schemas = program_procedure_json_schemas(runtime, program) if include_schemas else {}
    except KediParseError as error:
        return CompileResult(
            ok=False,
            message="Parse failed.",
            diagnostics=_diagnostics(error.diagnostics),
            rendered=render_parse_error(error, use_color=False),
            source_path=loaded.source_path,
        )
    except Exception as error:
        return CompileResult(
            ok=False,
            message=str(error),
            diagnostics=[],
            rendered=str(error),
            source_path=loaded.source_path,
        )
    return CompileResult(
        ok=True,
        message="Compiled successfully.",
        diagnostics=_diagnostics(program.parser_warnings),
        rendered=None,
        source_path=loaded.source_path,
        program=_program_summary(program),
        schemas=schemas,
    )


def _load_source(*, source: str | None, path: str | None) -> SourceInput | BaseToolResult:
    if (source is None) == (path is None):
        return BaseToolResult(
            ok=False,
            kind="parse",
            message="Provide exactly one of 'source' or 'path'.",
            diagnostics=[],
            rendered=None,
        )
    if source is not None:
        return SourceInput(text=source, source_path="<mcp-source>", is_file=False)
    assert path is not None
    source_path = _resolve_existing_file(path)
    if source_path is None:
        return BaseToolResult(
            ok=False,
            kind="parse",
            message=f"Kedi source file does not exist: {path}",
            diagnostics=[],
            rendered=None,
        )
    return SourceInput(
        text=source_path.read_text(encoding="utf-8"),
        source_path=str(source_path),
        is_file=True,
    )


def _resolve_existing_file(path: str) -> Path | None:
    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        return None
    return source_path


def _program_summary(program: Program | ProgramWithValidation) -> ProgramSummary:
    return ProgramSummary(
        procedures=[procedure.name for procedure in program.procedures],
        imports=[_import_name(module_import) for module_import in program.imports],
        exports=_export_names(program.exports),
        type_defs=[type_def.name for type_def in program.type_defs],
        profiles=sorted(program.profile_defs),
        parser_warning_count=len(program.parser_warnings),
        tests=[suite.procedure_name for suite in getattr(program, "tests", [])],
        evals=[suite.procedure_name for suite in getattr(program, "evals", [])],
    )


def _import_name(module_import: ModuleImport) -> str:
    return module_import.module


def _export_names(exports: list[ModuleExport]) -> list[str]:
    names: list[str] = []
    for module_export in exports:
        if module_export.export_all:
            names.append("*")
        names.extend(module_export.names)
    return names


def _diagnostics(diagnostics: list[KediDiagnostic]) -> list[DiagnosticPayload]:
    return [
        DiagnosticPayload(
            severity=diagnostic.severity,
            message=diagnostic.message,
            code=diagnostic.code,
            snippet=diagnostic.snippet,
            span=_span_payload(diagnostic.span),
        )
        for diagnostic in diagnostics
    ]


def _span_payload(span: Span | None) -> SpanPayload | None:
    if span is None:
        return None
    return SpanPayload(
        start_byte=span.start_byte,
        end_byte=span.end_byte,
        start_line=span.start_line,
        start_col=span.start_col,
        end_line=span.end_line,
        end_col=span.end_col,
        source_path=span.source_path,
        source_id=span.source_id,
    )


def _parse_error_result(error: KediParseError, source_path: str) -> ParseResult:
    return ParseResult(
        ok=False,
        message="Parse failed.",
        diagnostics=_diagnostics(error.diagnostics),
        rendered=render_parse_error(error, use_color=False),
        source_path=source_path,
    )


def _runtime_args(args: Mapping[str, str | int | float | bool] | None) -> CliArgs | None:
    if not args:
        return None
    argv: list[str] = []
    for key, value in sorted(args.items()):
        argv.append(f"--{key.replace('_', '-')}")
        if value is not True:
            argv.append(str(value))
    return parse_args(argv)
