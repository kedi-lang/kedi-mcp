from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import anyio
from fastmcp import FastMCP
from kedi.lang.ast import ModuleExport, ModuleImport

import kedi_mcp.__main__ as dunder_main
from kedi_mcp import server as server_module
from kedi_mcp.server import (
    _export_names,
    _import_name,
    _runtime_args,
    _span_payload,
    create_server,
)


async def _get_tool(server: FastMCP, name: str) -> Any:
    return await server.get_tool(name)


async def _call_tool(server: FastMCP, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await server.call_tool(name, arguments)
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def _run_tool(server: FastMCP, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return anyio.run(_call_tool, server, name, arguments)


def test_create_server_registers_public_tools() -> None:
    server = create_server()

    async def check_tools() -> None:
        for name in {
            "kedi_health",
            "kedi_parse",
            "kedi_compile",
            "kedi_schema",
            "kedi_run",
            "kedi_test",
            "kedi_eval",
        }:
            assert await _get_tool(server, name) is not None

    anyio.run(check_tools)


def test_kedi_health_reports_executables() -> None:
    result = _run_tool(create_server(), "kedi_health", {})

    assert result["ok"] is True
    assert result["kind"] == "health"
    assert result["fastmcp"] is True
    assert result["python"]


def test_kedi_parse_source_success() -> None:
    result = _run_tool(
        create_server(),
        "kedi_parse",
        {"source": "@main(name: str) -> str:\n  = Hello <name>\n"},
    )

    assert result["ok"] is True
    assert result["source_path"] == "<mcp-source>"
    assert result["program"]["procedures"] == ["main"]


def test_kedi_parse_rejects_ambiguous_source_inputs(tmp_path: Path) -> None:
    source_path = tmp_path / "sample.kedi"
    source_path.write_text("= ok\n", encoding="utf-8")

    result = _run_tool(
        create_server(),
        "kedi_parse",
        {"source": "= ok\n", "path": str(source_path)},
    )

    assert result["ok"] is False
    assert result["message"] == "Provide exactly one of 'source' or 'path'."


def test_kedi_parse_source_failure_returns_diagnostics() -> None:
    result = _run_tool(create_server(), "kedi_parse", {"source": "@main(:\n  = ok\n"})

    assert result["ok"] is False
    assert result["kind"] == "parse"
    assert result["message"]
    assert result["diagnostics"]
    assert result["rendered"]


def test_kedi_compile_includes_schema() -> None:
    result = _run_tool(
        create_server(),
        "kedi_compile",
        {"source": '@main(name: str = `"Ada"`) -> str:\n  = Hello <name>\n'},
    )

    assert result["ok"] is True
    assert result["schemas"]["main"]["properties"]["name"]["default"] == "Ada"


def test_kedi_schema_file_success(tmp_path: Path) -> None:
    source_path = tmp_path / "schema.kedi"
    source_path.write_text("@search(query: str) -> str:\n  = <query>\n", encoding="utf-8")

    result = _run_tool(create_server(), "kedi_schema", {"path": str(source_path)})

    assert result["ok"] is True
    assert result["source_path"] == str(source_path.resolve())
    assert result["schemas"]["search"]["properties"]["query"]["type"] == "string"


def test_kedi_schema_rejects_missing_source_input() -> None:
    result = _run_tool(create_server(), "kedi_schema", {})

    assert result["ok"] is False
    assert result["source_path"] == "<invalid>"


def test_kedi_schema_parse_failure_returns_diagnostics() -> None:
    result = _run_tool(create_server(), "kedi_schema", {"source": "@main(:\n  = ok\n"})

    assert result["ok"] is False
    assert result["diagnostics"]


def test_kedi_schema_compile_failure_is_structured(monkeypatch: Any) -> None:
    def fail_compile(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("compile boom")

    monkeypatch.setattr(server_module, "compile_program", fail_compile)

    result = _run_tool(create_server(), "kedi_schema", {"source": "= ok\n"})

    assert result["ok"] is False
    assert result["message"] == "compile boom"


def test_kedi_run_source_success() -> None:
    result = _run_tool(create_server(), "kedi_run", {"source": "= ok\n"})

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["output"] == "ok"


def test_kedi_run_file_success(tmp_path: Path) -> None:
    source_path = tmp_path / "run.kedi"
    source_path.write_text("= ok\n", encoding="utf-8")

    result = _run_tool(create_server(), "kedi_run", {"path": str(source_path)})

    assert result["ok"] is True
    assert result["output"] == "ok"


def test_kedi_run_file_missing_returns_structured_failure() -> None:
    result = _run_tool(create_server(), "kedi_run", {"path": "missing.kedi"})

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert "does not exist" in result["message"]


def test_kedi_run_parse_failure_returns_diagnostics() -> None:
    result = _run_tool(create_server(), "kedi_run", {"source": "@main(:\n  = ok\n"})

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["diagnostics"]


def test_kedi_run_execution_failure_is_structured(monkeypatch: Any) -> None:
    def fail_run_source(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("run boom")

    monkeypatch.setattr(server_module, "run_source_cli", fail_run_source)

    result = _run_tool(create_server(), "kedi_run", {"source": "= ok\n"})

    assert result["ok"] is False
    assert result["message"] == "run boom"


def test_kedi_compile_rejects_missing_source_input() -> None:
    result = _run_tool(create_server(), "kedi_compile", {})

    assert result["ok"] is False
    assert result["source_path"] == "<invalid>"


def test_kedi_compile_parse_failure_returns_diagnostics() -> None:
    result = _run_tool(create_server(), "kedi_compile", {"source": "@main(:\n  = ok\n"})

    assert result["ok"] is False
    assert result["diagnostics"]


def test_kedi_compile_runtime_failure_is_structured(monkeypatch: Any) -> None:
    def fail_compile(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("compile boom")

    monkeypatch.setattr(server_module, "compile_program", fail_compile)

    result = _run_tool(create_server(), "kedi_compile", {"source": "= ok\n"})

    assert result["ok"] is False
    assert result["message"] == "compile boom"


def test_kedi_test_file_path(tmp_path: Path) -> None:
    source_path = tmp_path / "tests.kedi"
    source_path.write_text(
        "@main() -> str:\n  = ok\n\n@test: main:\n  > case: ok:\n    `assert main() == 'ok'`\n",
        encoding="utf-8",
    )

    result = _run_tool(create_server(), "kedi_test", {"path": str(source_path)})

    assert result["ok"] is True
    assert result["exit_code"] == 0


def test_kedi_test_missing_file() -> None:
    result = _run_tool(create_server(), "kedi_test", {"path": "missing.kedi"})

    assert result["ok"] is False
    assert result["exit_code"] == 2


def test_kedi_test_runner_exception_is_structured(tmp_path: Path, monkeypatch: Any) -> None:
    source_path = tmp_path / "tests.kedi"
    source_path.write_text("= ok\n", encoding="utf-8")

    def fail_tests(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("test boom")

    monkeypatch.setattr(server_module, "run_tests_cli", fail_tests)

    result = _run_tool(create_server(), "kedi_test", {"path": str(source_path)})

    assert result["ok"] is False
    assert result["message"] == "test boom"


def test_kedi_eval_missing_file() -> None:
    result = _run_tool(create_server(), "kedi_eval", {"path": "missing.kedi"})

    assert result["ok"] is False
    assert result["kind"] == "eval"
    assert result["exit_code"] == 2


def test_kedi_eval_runner_exception_is_structured(tmp_path: Path, monkeypatch: Any) -> None:
    source_path = tmp_path / "eval.kedi"
    source_path.write_text("= ok\n", encoding="utf-8")

    def fail_evals(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("eval boom")

    monkeypatch.setattr(server_module, "run_evals_cli", fail_evals)

    result = _run_tool(create_server(), "kedi_eval", {"path": str(source_path)})

    assert result["ok"] is False
    assert result["message"] == "eval boom"


def test_kedi_eval_runner_nonzero_is_structured(tmp_path: Path, monkeypatch: Any) -> None:
    source_path = tmp_path / "eval.kedi"
    source_path.write_text("= ok\n", encoding="utf-8")

    def fail_evals(*args: Any, **kwargs: Any) -> tuple[int, str]:
        del args, kwargs
        return 1, "bad eval"

    monkeypatch.setattr(server_module, "run_evals_cli", fail_evals)

    result = _run_tool(create_server(), "kedi_eval", {"path": str(source_path)})

    assert result["ok"] is False
    assert result["message"] == "Kedi evals failed."
    assert result["output"] == "bad eval"


def test_runtime_args_are_deterministic() -> None:
    runtime_args = _runtime_args({"b": 2, "a": True})

    assert runtime_args is not None
    assert runtime_args.a is True
    assert runtime_args.b == "2"


def test_export_names_and_span_none_helpers() -> None:
    assert _import_name(ModuleImport(module="math")) == "math"
    assert _export_names(
        [
            ModuleExport(names=["plain"], export_all=False),
            ModuleExport(names=["star"], export_all=True),
        ]
    ) == ["plain", "*", "star"]
    assert _span_payload(None) is None


def test_main_forwards_transport_kwargs(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeServer:
        def run(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(server_module, "create_server", FakeServer)

    server_module.main(["--transport", "sse", "--host", "127.0.0.1", "--port", "9000"])

    assert calls == [{"transport": "sse", "host": "127.0.0.1", "port": 9000}]


def test_main_defaults_to_stdio_without_transport_kwargs(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeServer:
        def run(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(server_module, "create_server", FakeServer)

    server_module.main([])

    assert calls == [{"transport": "stdio"}]


def test_dunder_main_import_exposes_main() -> None:
    assert dunder_main.main is server_module.main


def test_dunder_main_invokes_server_main(monkeypatch: Any) -> None:
    calls: list[str] = []

    monkeypatch.setattr(server_module, "main", lambda: calls.append("called"))

    runpy.run_module("kedi_mcp.__main__", run_name="__main__")

    assert calls == ["called"]
