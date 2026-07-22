"""Architecture checks for bid-domain orchestration modules."""

from pathlib import Path

ORCHESTRATION_ROOT = (
    Path(__file__).parents[3] / "src" / "bid_system" / "orchestration"
)
REQUIRED_ORCHESTRATION_FILES = frozenset(
    {
        "agents/evidence_review_agent.py",
        "agents/plan_explainer_agent.py",
        "agents/product_document_agent.py",
        "agents/tender_document_agent.py",
        "policies/budgets.py",
        "policies/human_gate.py",
        "policies/tool_permissions.py",
        "tools/document_tools.py",
        "tools/matching_tools.py",
        "tools/planning_tools.py",
        "tools/product_tools.py",
        "tools/tender_tools.py",
        "workflows/generate_bid_plan.py",
        "workflows/ingest_product_document.py",
        "workflows/ingest_tender_document.py",
    }
)


def test_orchestration_contains_documented_module_files() -> None:
    relative_files = {
        path.relative_to(ORCHESTRATION_ROOT).as_posix()
        for path in ORCHESTRATION_ROOT.rglob("*.py")
    }

    assert relative_files >= REQUIRED_ORCHESTRATION_FILES
