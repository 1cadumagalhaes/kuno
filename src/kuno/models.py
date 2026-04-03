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
    STATEFULSETS = "statefulsets"
    SERVICES = "services"
    PVC = "pvc"


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


@dataclass(slots=True)
class StatefulSetSummary:
    name: str
    ready: str
    updated: int
    current: int
    age: str
    containers: str
    cpu: str
    memory: str


@dataclass(slots=True)
class ServiceSummary:
    name: str
    type: str
    cluster_ip: str
    ports: str
    age: str
    selector: str


@dataclass(slots=True)
class PvcSummary:
    name: str
    status: str
    volume: str
    capacity: str
    access: str
    storage_class: str
    age: str
