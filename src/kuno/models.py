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


@dataclass(slots=True)
class ContainerSummary:
    name: str
    pod: str
    ready: str
    state: str
    restarts: int
    image: str
    cpu: str
    memory: str


class ExplorerView(StrEnum):
    CONTAINERS = "containers"
    CONTEXTS = "contexts"
    NAMESPACES = "namespaces"
    PODS = "pods"
    DEPLOYMENTS = "deployments"
    STATEFULSETS = "statefulsets"
    SERVICES = "services"
    PVC = "pvc"
    SECRETS = "secrets"


@dataclass(slots=True)
class ContextSummary:
    name: str
    cluster: str
    user: str
    namespace: str
    current: str


@dataclass(slots=True)
class NamespaceSummary:
    name: str
    status: str
    age: str
    current: str


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


@dataclass(slots=True)
class SecretSummary:
    name: str
    type: str
    data_items: int
    immutable: str
    age: str
