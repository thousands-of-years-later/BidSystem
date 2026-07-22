import ast
from pathlib import Path

AGENT_RUNTIME_ROOT = (
    Path(__file__).parents[3] / "src" / "bid_system" / "agent_runtime"
)
ALLOWED_RUNTIME_DIRECTORIES = frozenset(
    {"core", "tools", "context", "sessions", "skills", "observability"}
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
