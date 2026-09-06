from dataclasses import dataclass, field


class PhrasecutError(ValueError):
    """An actionable input or processing error."""


@dataclass
class Phrase:
    id: int
    text: str
    translation: str = ""
    section: str = ""


@dataclass
class Word:
    text: str
    start: float
    end: float
    probability: float = 1.0


@dataclass
class Cut:
    id: int
    start: float | None
    end: float | None
    recognized: str = ""
    coverage: float = 0.0
    issues: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)
