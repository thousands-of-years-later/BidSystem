from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from bid_system.agent_runtime.core.agent import (
    RunContext,
    RunIdentity,
    RuntimeVersions,
    SkillVersion,
)


def test_run_context_keeps_immutable_identity_and_versions() -> None:
    versions = RuntimeVersions(
        model_name="extractor",
        model_version="2026-07-01",
        prompt_name="product-fact-extract",
        prompt_version="v1",
        skills=(SkillVersion(name="fact-extraction", version="v2"),),
    )
    context = RunContext(
        identity=RunIdentity(
            run_id="run-1",
            request_id="request-1",
            trace_id="1" * 32,
            task_id="task-1",
            tenant_id="tenant-1",
            actor_id="user-1",
        ),
        versions=versions,
    )

    assert context.identity.task_id == "task-1"
    assert context.versions.skills[0].name == "fact-extraction"
    with pytest.raises(FrozenInstanceError):
        context.identity.__setattr__("run_id", "changed")


@pytest.mark.parametrize("field_name", ["run_id", "request_id", "trace_id"])
def test_run_identity_rejects_blank_required_identifiers(field_name: str) -> None:
    values = {"run_id": "run-1", "request_id": "request-1", "trace_id": "1" * 32}
    values[field_name] = " "

    with pytest.raises(ValueError, match=field_name):
        RunIdentity(**values)


def test_runtime_versions_reject_duplicate_skill_names() -> None:
    with pytest.raises(ValueError, match="skill names"):
        RuntimeVersions(
            model_name="extractor",
            model_version="2026-07-01",
            prompt_name="product-fact-extract",
            prompt_version="v1",
            skills=(
                SkillVersion(name="fact-extraction", version="v1"),
                SkillVersion(name="fact-extraction", version="v2"),
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "factory"),
    [
        (
            "model_name",
            lambda: RuntimeVersions(
                model_name=" ",
                model_version="2026-07-01",
                prompt_name="product-fact-extract",
                prompt_version="v1",
            ),
        ),
        (
            "model_version",
            lambda: RuntimeVersions(
                model_name="extractor",
                model_version=" ",
                prompt_name="product-fact-extract",
                prompt_version="v1",
            ),
        ),
        (
            "prompt_name",
            lambda: RuntimeVersions(
                model_name="extractor",
                model_version="2026-07-01",
                prompt_name=" ",
                prompt_version="v1",
            ),
        ),
        (
            "prompt_version",
            lambda: RuntimeVersions(
                model_name="extractor",
                model_version="2026-07-01",
                prompt_name="product-fact-extract",
                prompt_version=" ",
            ),
        ),
    ],
)
def test_runtime_versions_reject_blank_values(
    field_name: str,
    factory: Callable[[], RuntimeVersions],
) -> None:
    with pytest.raises(ValueError, match=field_name):
        factory()
