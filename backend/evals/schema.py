"""What one eval case is, and what running it produced."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    """One lesson situation. Only the tutor's reply to the last learner message is graded."""

    id: str
    tag: str
    turns: tuple[str, ...]
    # Concrete yes/no claims about the reply, for the judge.
    criteria: tuple[str, ...]
    level: str = "B1"
    topic: str = "Job interview preparation"
    minutes: int = 15
    # How far into the lesson the graded message is sent.
    elapsed_minutes: float = 1
    preferences: tuple[tuple[str, str], ...] = ()
    # How many `record_mistake` calls the graded turn may make.
    mistakes_min: int = 0
    mistakes_max: int | None = None
    # Each group must match at least one correction; a group lists accepted wordings.
    corrected_any: tuple[tuple[str, ...], ...] = ()
    # The reply may name two wordings when both are common ("I am 30", "I'm 30").
    allow_variants: bool = False
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    # The tutor's closing message: no question, and the lesson ends after it.
    expect_time_up: bool = False


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class Turn:
    learner: str
    reply: str
    tool_calls: tuple[ToolCall, ...]


@dataclass
class CaseRun:
    turns: list[Turn]
    system_prompt: str
    time_up: bool = False
    stop_reason: str | None = None
    model: str | None = None
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def graded(self) -> Turn:
        return self.turns[-1]
