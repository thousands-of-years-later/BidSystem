import pytest
from pydantic import BaseModel, ConfigDict

from bid_system.agent_runtime.context.run import RunContext, RunIdentity, RuntimeVersions
from bid_system.agent_runtime.core.llm import (
    MessageRole,
    ModelMessage,
    StructuredOutputRequest,
    StructuredOutputResult,
)


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_code: str


def _context() -> RunContext:
    return RunContext(
        identity=RunIdentity(run_id="run-1", request_id="request-1", trace_id="1" * 32),
        versions=RuntimeVersions(
            model_name="extractor",
            model_version="2026-07-01",
            prompt_name="product-fact-extract",
            prompt_version="v1",
        ),
    )


def test_structured_request_keeps_schema_and_immutable_messages() -> None:
    message = ModelMessage(role=MessageRole.USER, content="Extract the candidate")

    request = StructuredOutputRequest(
        messages=(message,),
        output_schema=ExtractionCandidate,
    )

    assert request.messages == (message,)
    assert request.output_schema is ExtractionCandidate


def test_model_message_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="content"):
        ModelMessage(role=MessageRole.USER, content="   ")


def test_structured_request_rejects_empty_messages() -> None:
    with pytest.raises(ValueError, match="messages"):
        StructuredOutputRequest(messages=(), output_schema=ExtractionCandidate)


def test_structured_result_requires_context_model_identity() -> None:
    context = _context()
    candidate = ExtractionCandidate(model_code="NL-200")

    result = StructuredOutputResult(output=candidate, context=context)

    assert result.output == candidate
    assert result.context.versions.model_name == "extractor"
    assert result.context.versions.model_version == "2026-07-01"
