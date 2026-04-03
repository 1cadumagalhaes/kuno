from dataclasses import dataclass
from enum import StrEnum


@dataclass(slots=True)
class StartupConfig:
    context: str | None = None
    namespace: str | None = None


@dataclass(slots=True)
class PodSummary:
    name: str
    ready: str
    status: str
    restarts: int
    age: str
    containers: str
    cpu: str
    memory: str


class ExplorerView(StrEnum):
    PODS = "pods"
    DEPLOYMENTS = "deployments"


@dataclass(slots=True)
class DeploymentSummary:
    name: str
    ready: str
    up_to_date: int
    available: int
    age: str
    containers: str
    cpu: str
    memory: str
