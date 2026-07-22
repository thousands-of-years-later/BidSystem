import ast
from pathlib import Path

AGENT_RUNTIME_ROOT = (
    Path(__file__).parents[3] / "src" / "bid_system" / "agent_runtime"
)
ALLOWED_RUNTIME_DIRECTORIES = frozenset(
    {"core", "tools", "context", "sessions", "skills", "observability"}
)
REQUIRED_RUNTIME_FILES = frozenset(
    {
        "context/builder.py",
        "context/history.py",
        "context/token_counter.py",
        "context/truncator.py",
        "core/agent.py",
        "core/lifecycle.py",
        "core/llm.py",
        "core/streaming.py",
        "observability/events.py",
        "observability/metrics.py",
        "observability/traces.py",
        "sessions/checkpoints.py",
        "sessions/store.py",
        "skills/loader.py",
        "skills/manifest.py",
        "tools/base.py",
        "tools/circuit_breaker.py",
        "tools/executor.py",
        "tools/registry.py",
        "tools/response.py",
    }
)
FORBIDDEN_IMPORT_PREFIXES = (
    "bid_system.modules",
    "bid_system.orchestration",
    "bid_system.entrypoints",
    "bid_system.platform",
)


def test_agent_runtime_contains_architecture_capability_groups() -> None:
    directory_names = {
        path.name
        for path in AGENT_RUNTIME_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }

    assert directory_names == ALLOWED_RUNTIME_DIRECTORIES


def test_agent_runtime_contains_documented_module_files() -> None:
    relative_files = {
        path.relative_to(AGENT_RUNTIME_ROOT).as_posix()
        for path in AGENT_RUNTIME_ROOT.rglob("*.py")
    }

    assert relative_files >= REQUIRED_RUNTIME_FILES
    assert "context/run.py" not in relative_files


def test_agent_runtime_does_not_depend_on_business_or_platform_implementations() -> None:
    violations: list[str] = []
    for source_path in AGENT_RUNTIME_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_module = node.module
                if imported_module is not None and imported_module.startswith(
                    FORBIDDEN_IMPORT_PREFIXES
                ):
                    violations.append(f"{source_path}:{node.lineno}:{imported_module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(f"{source_path}:{node.lineno}:{alias.name}")

    assert violations == []
