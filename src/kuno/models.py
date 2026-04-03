from dataclasses import dataclass


@dataclass(slots=True)
class StartupConfig:
    context: str | None = None
    namespace: str | None = None


@dataclass(slots=True)
class PodSummary:
    name: str
    phase: str
