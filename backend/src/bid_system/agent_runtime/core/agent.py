"""Agent execution identity, immutable run context, and version provenance."""

from dataclasses import dataclass


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _validate_optional(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_blank(value, field_name)


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """Correlation and ownership identifiers for one runtime execution."""

    run_id: str
    request_id: str
    trace_id: str
    task_id: str | None = None
    tenant_id: str | None = None
    actor_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.run_id, "run_id")
        _require_non_blank(self.request_id, "request_id")
        _require_non_blank(self.trace_id, "trace_id")
        _validate_optional(self.task_id, "task_id")
        _validate_optional(self.tenant_id, "tenant_id")
        _validate_optional(self.actor_id, "actor_id")


@dataclass(frozen=True, slots=True)
class SkillVersion:
    """One explicitly loaded skill and its immutable version."""

    name: str
    version: str

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "skill name")
        _require_non_blank(self.version, "skill version")


@dataclass(frozen=True, slots=True)
class RuntimeVersions:
    """Model, prompt, and optional skill versions fixed for one run."""

    model_name: str
    model_version: str
    prompt_name: str
    prompt_version: str
    skills: tuple[SkillVersion, ...] = ()

    def __post_init__(self) -> None:
        _require_non_blank(self.model_name, "model_name")
        _require_non_blank(self.model_version, "model_version")
        _require_non_blank(self.prompt_name, "prompt_name")
        _require_non_blank(self.prompt_version, "prompt_version")
        skill_names = tuple(skill.name for skill in self.skills)
        if len(set(skill_names)) != len(skill_names):
            raise ValueError("skill names must be unique")


@dataclass(frozen=True, slots=True)
class RunContext:
    """Minimal context passed to model and tool boundaries."""

    identity: RunIdentity
    versions: RuntimeVersions
