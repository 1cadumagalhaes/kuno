from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from kubernetes_asyncio.client import AppsV1Api, CoreV1Api

from kuno.models import (
    ContainerSummary,
    ContextSummary,
    DeploymentSummary,
    NamespaceSummary,
    PodSummary,
    PvcSummary,
    SecretSummary,
    ServiceSummary,
    StatefulSetSummary,
)


class HasCoreV1(Protocol):
    core_v1: CoreV1Api | Any | None


class HasAppsV1(Protocol):
    apps_v1: AppsV1Api | Any | None


async def list_pods(kube_client: HasCoreV1, namespace: str) -> list[PodSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pod_list = await kube_client.core_v1.list_namespaced_pod(namespace)
    current = datetime.now(UTC)
    return [pod_summary_from_api_item(item, now=current) for item in pod_list.items]


async def list_pod_containers(
    kube_client: HasCoreV1, namespace: str, pod_name: str
) -> list[ContainerSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pod = await kube_client.core_v1.read_namespaced_pod(pod_name, namespace)
    return container_summaries_from_pod(pod)


async def read_pod_logs(
    kube_client: HasCoreV1,
    namespace: str,
    pod_name: str,
    *,
    container_name: str | None = None,
    tail_lines: int = 500,
    timestamps: bool = False,
) -> str:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    kwargs: dict[str, Any] = {"tail_lines": tail_lines, "timestamps": timestamps}
    if container_name is not None:
        kwargs["container"] = container_name
    result = await kube_client.core_v1.read_namespaced_pod_log(pod_name, namespace, **kwargs)
    return result if isinstance(result, str) else ""


async def list_namespaces(kube_client: HasCoreV1) -> list[str]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    namespace_list = await kube_client.core_v1.list_namespace()
    names = []
    for item in namespace_list.items:
        metadata = getattr(item, "metadata", None)
        name = getattr(metadata, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
    return sorted(names)


async def list_namespace_summaries(
    kube_client: HasCoreV1, *, current_namespace: str | None
) -> list[NamespaceSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    namespace_list = await kube_client.core_v1.list_namespace()
    current = datetime.now(UTC)
    return [
        namespace_summary_from_api_item(item, now=current, current_namespace=current_namespace)
        for item in namespace_list.items
    ]


async def list_services(kube_client: HasCoreV1, namespace: str) -> list[ServiceSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    service_list = await kube_client.core_v1.list_namespaced_service(namespace)
    current = datetime.now(UTC)
    return [service_summary_from_api_item(item, now=current) for item in service_list.items]


async def list_pvcs(kube_client: HasCoreV1, namespace: str) -> list[PvcSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pvc_list = await kube_client.core_v1.list_namespaced_persistent_volume_claim(namespace)
    current = datetime.now(UTC)
    return [pvc_summary_from_api_item(item, now=current) for item in pvc_list.items]


async def list_secrets(kube_client: HasCoreV1, namespace: str) -> list[SecretSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    secret_list = await kube_client.core_v1.list_namespaced_secret(namespace)
    current = datetime.now(UTC)
    return [secret_summary_from_api_item(item, now=current) for item in secret_list.items]


async def list_deployments(kube_client: HasAppsV1, namespace: str) -> list[DeploymentSummary]:
    if kube_client.apps_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    deployment_list = await kube_client.apps_v1.list_namespaced_deployment(namespace)
    current = datetime.now(UTC)
    return [deployment_summary_from_api_item(item, now=current) for item in deployment_list.items]


async def list_statefulsets(kube_client: HasAppsV1, namespace: str) -> list[StatefulSetSummary]:
    if kube_client.apps_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    statefulset_list = await kube_client.apps_v1.list_namespaced_stateful_set(namespace)
    current = datetime.now(UTC)
    return [statefulset_summary_from_api_item(item, now=current) for item in statefulset_list.items]


def pod_summary_from_api_item(item: Any, now: datetime | None = None) -> PodSummary:
    metadata = getattr(item, "metadata", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    phase = getattr(status, "phase", None)
    reason = getattr(status, "reason", None)
    container_statuses = getattr(status, "container_statuses", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)
    spec = getattr(item, "spec", None)
    containers = getattr(spec, "containers", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Pod is missing a valid name")

    if not isinstance(phase, str) or not phase:
        phase = "Unknown"

    return PodSummary(
        name=name,
        ready=pod_ready(container_statuses),
        status=reason if isinstance(reason, str) and reason else phase,
        restarts=pod_restarts(container_statuses),
        age=format_age(creation_timestamp, now=now),
        containers=container_summary(containers),
        cpu=format_cpu_requests(containers),
        memory=format_memory_requests(containers),
    )


def container_summaries_from_pod(item: Any) -> list[ContainerSummary]:
    metadata = getattr(item, "metadata", None)
    spec = getattr(item, "spec", None)
    status = getattr(item, "status", None)
    pod_name = getattr(metadata, "name", None)
    containers = getattr(spec, "containers", None)
    statuses = getattr(status, "container_statuses", None)

    if not isinstance(pod_name, str) or not pod_name:
        raise ValueError("Pod is missing a valid name")

    status_by_name: dict[str, Any] = {}
    if isinstance(statuses, list):
        for container_status in statuses:
            name = getattr(container_status, "name", None)
            if isinstance(name, str) and name:
                status_by_name[name] = container_status

    summaries: list[ContainerSummary] = []
    if not isinstance(containers, list):
        return summaries

    for container in containers:
        name = getattr(container, "name", None)
        if not isinstance(name, str) or not name:
            continue
        container_status = status_by_name.get(name)
        summaries.append(
            ContainerSummary(
                name=name,
                pod=pod_name,
                ready="yes" if getattr(container_status, "ready", False) else "no",
                state=container_state(container_status),
                restarts=int(getattr(container_status, "restart_count", 0) or 0),
                image=string_or_default(getattr(container, "image", None), "-"),
                cpu=format_cpu_requests([container]),
                memory=format_memory_requests([container]),
            )
        )
    return summaries


def deployment_summary_from_api_item(item: Any, now: datetime | None = None) -> DeploymentSummary:
    metadata = getattr(item, "metadata", None)
    spec = getattr(item, "spec", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)
    containers = getattr(getattr(spec, "template", None), "spec", None)
    pod_containers = getattr(containers, "containers", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Deployment is missing a valid name")

    desired = int(getattr(spec, "replicas", 0) or 0)
    ready = int(getattr(status, "ready_replicas", 0) or 0)
    updated = int(getattr(status, "updated_replicas", 0) or 0)
    available = int(getattr(status, "available_replicas", 0) or 0)

    return DeploymentSummary(
        name=name,
        ready=f"{ready}/{desired}",
        up_to_date=updated,
        available=available,
        age=format_age(creation_timestamp, now=now),
        containers=container_summary(pod_containers),
        cpu=format_cpu_requests(pod_containers),
        memory=format_memory_requests(pod_containers),
    )


def statefulset_summary_from_api_item(item: Any, now: datetime | None = None) -> StatefulSetSummary:
    metadata = getattr(item, "metadata", None)
    spec = getattr(item, "spec", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)
    containers = getattr(getattr(spec, "template", None), "spec", None)
    pod_containers = getattr(containers, "containers", None)

    if not isinstance(name, str) or not name:
        raise ValueError("StatefulSet is missing a valid name")

    desired = int(getattr(spec, "replicas", 0) or 0)
    ready = int(getattr(status, "ready_replicas", 0) or 0)
    updated = int(getattr(status, "updated_replicas", 0) or 0)
    current = int(getattr(status, "current_replicas", 0) or 0)

    return StatefulSetSummary(
        name=name,
        ready=f"{ready}/{desired}",
        updated=updated,
        current=current,
        age=format_age(creation_timestamp, now=now),
        containers=container_summary(pod_containers),
        cpu=format_cpu_requests(pod_containers),
        memory=format_memory_requests(pod_containers),
    )


def service_summary_from_api_item(item: Any, now: datetime | None = None) -> ServiceSummary:
    metadata = getattr(item, "metadata", None)
    spec = getattr(item, "spec", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Service is missing a valid name")

    return ServiceSummary(
        name=name,
        type=string_or_default(getattr(spec, "type", None), "ClusterIP"),
        cluster_ip=string_or_default(getattr(spec, "cluster_ip", None), "-"),
        ports=service_ports_summary(getattr(spec, "ports", None)),
        age=format_age(creation_timestamp, now=now),
        selector=selector_summary(getattr(spec, "selector", None)),
    )


def pvc_summary_from_api_item(item: Any, now: datetime | None = None) -> PvcSummary:
    metadata = getattr(item, "metadata", None)
    spec = getattr(item, "spec", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)
    capacity = getattr(status, "capacity", None)

    if not isinstance(name, str) or not name:
        raise ValueError("PVC is missing a valid name")

    size = "-"
    if isinstance(capacity, dict):
        size = string_or_default(capacity.get("storage"), "-")

    return PvcSummary(
        name=name,
        status=string_or_default(getattr(status, "phase", None), "Unknown"),
        volume=string_or_default(getattr(spec, "volume_name", None), "-"),
        capacity=size,
        access=access_modes_summary(getattr(spec, "access_modes", None)),
        storage_class=string_or_default(getattr(spec, "storage_class_name", None), "-"),
        age=format_age(creation_timestamp, now=now),
    )


def container_state(container_status: Any) -> str:
    if container_status is None:
        return "Unknown"
    state = getattr(container_status, "state", None)
    if state is None:
        return "Unknown"
    for name in ("running", "waiting", "terminated"):
        if getattr(state, name, None) is not None:
            return name.capitalize()
    return "Unknown"


def namespace_summary_from_api_item(
    item: Any, *, now: datetime | None = None, current_namespace: str | None
) -> NamespaceSummary:
    metadata = getattr(item, "metadata", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Namespace is missing a valid name")

    return NamespaceSummary(
        name=name,
        status=string_or_default(getattr(status, "phase", None), "Active"),
        age=format_age(creation_timestamp, now=now),
        current="*" if current_namespace == name else "",
    )


def secret_summary_from_api_item(item: Any, now: datetime | None = None) -> SecretSummary:
    metadata = getattr(item, "metadata", None)
    name = getattr(metadata, "name", None)
    creation_timestamp = getattr(metadata, "creation_timestamp", None)
    data = getattr(item, "data", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Secret is missing a valid name")

    return SecretSummary(
        name=name,
        type=string_or_default(getattr(item, "type", None), "Opaque"),
        data_items=len(data) if isinstance(data, dict) else 0,
        immutable="yes" if getattr(item, "immutable", False) else "no",
        age=format_age(creation_timestamp, now=now),
    )


def pod_ready(container_statuses: Any) -> str:
    if not isinstance(container_statuses, list) or not container_statuses:
        return "0/0"

    ready = sum(1 for status in container_statuses if getattr(status, "ready", False))
    return f"{ready}/{len(container_statuses)}"


def pod_restarts(container_statuses: Any) -> int:
    if not isinstance(container_statuses, list):
        return 0

    return sum(int(getattr(status, "restart_count", 0) or 0) for status in container_statuses)


def format_age(value: Any, now: datetime | None = None) -> str:
    if not isinstance(value, datetime):
        return "-"

    current = now or datetime.now(UTC)
    timestamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    age_seconds = max(int((current - timestamp).total_seconds()), 0)
    if age_seconds < 60:
        return f"{age_seconds}s"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m"
    if age_seconds < 86400:
        return f"{age_seconds // 3600}h"
    return f"{age_seconds // 86400}d"


def container_summary(containers: Any) -> str:
    if not isinstance(containers, list) or not containers:
        return "-"

    names = [
        name
        for container in containers
        if isinstance((name := getattr(container, "name", None)), str)
    ]
    if not names:
        return "-"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return ",".join(names)
    return f"{names[0]},+{len(names) - 1}"


def truncate_for_table(value: str, max_length: int = 56) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return "." * max_length
    return f"{value[: max_length - 3]}..."


def selector_summary(selector: Any) -> str:
    if not isinstance(selector, dict) or not selector:
        return "-"
    parts = [f"{key}={value}" for key, value in sorted(selector.items())]
    return truncate_for_table(",".join(parts), max_length=40)


def service_ports_summary(ports: Any) -> str:
    if not isinstance(ports, list) or not ports:
        return "-"
    values: list[str] = []
    for port in ports:
        number = getattr(port, "port", None)
        protocol = string_or_default(getattr(port, "protocol", None), "TCP")
        if isinstance(number, int):
            values.append(f"{number}/{protocol}")
    if not values:
        return "-"
    return truncate_for_table(",".join(values), max_length=32)


def access_modes_summary(modes: Any) -> str:
    if not isinstance(modes, list) or not modes:
        return "-"
    values = [mode for mode in modes if isinstance(mode, str) and mode]
    if not values:
        return "-"
    return truncate_for_table(",".join(values), max_length=24)


def string_or_default(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def format_cpu_requests(containers: Any) -> str:
    total = Decimal(0)
    if isinstance(containers, list):
        for container in containers:
            resources = getattr(container, "resources", None)
            requests = getattr(resources, "requests", None)
            if isinstance(requests, dict):
                total += parse_cpu_quantity(requests.get("cpu"))

    if total == 0:
        return "-"

    millicores = int(total * 1000)
    if millicores % 1000 == 0:
        return str(millicores // 1000)
    return f"{millicores}m"


def format_memory_requests(containers: Any) -> str:
    total = 0
    if isinstance(containers, list):
        for container in containers:
            resources = getattr(container, "resources", None)
            requests = getattr(resources, "requests", None)
            if isinstance(requests, dict):
                total += parse_memory_quantity(requests.get("memory"))

    if total == 0:
        return "-"

    gib = 1024**3
    mib = 1024**2
    if total >= gib and total % gib == 0:
        return f"{total // gib}Gi"
    return f"{total // mib}Mi"


def parse_cpu_quantity(value: Any) -> Decimal:
    if not isinstance(value, str) or not value:
        return Decimal(0)
    if value.endswith("m"):
        return Decimal(value[:-1]) / Decimal(1000)
    return Decimal(value)


def parse_memory_quantity(value: Any) -> int:
    if not isinstance(value, str) or not value:
        return 0

    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
    }
    for suffix, factor in suffixes.items():
        if value.endswith(suffix):
            return int(Decimal(value[: -len(suffix)]) * factor)
    return int(Decimal(value))


def render_pod_details(pod: PodSummary) -> str:
    return (
        "pod\n"
        f"name: {pod.name}\n"
        f"ready: {pod.ready}\n"
        f"status: {pod.status}\n"
        f"restarts: {pod.restarts}\n"
        f"age: {pod.age}\n"
        f"containers: {pod.containers}\n"
        f"cpu: {pod.cpu}\n"
        f"memory: {pod.memory}"
    )


def render_deployment_details(deployment: DeploymentSummary) -> str:
    return (
        "deployment\n"
        f"name: {deployment.name}\n"
        f"ready: {deployment.ready}\n"
        f"up-to-date: {deployment.up_to_date}\n"
        f"available: {deployment.available}\n"
        f"age: {deployment.age}\n"
        f"containers: {deployment.containers}\n"
        f"cpu: {deployment.cpu}\n"
        f"memory: {deployment.memory}"
    )


def render_statefulset_details(statefulset: StatefulSetSummary) -> str:
    return (
        "statefulset\n"
        f"name: {statefulset.name}\n"
        f"ready: {statefulset.ready}\n"
        f"updated: {statefulset.updated}\n"
        f"current: {statefulset.current}\n"
        f"age: {statefulset.age}\n"
        f"containers: {statefulset.containers}\n"
        f"cpu: {statefulset.cpu}\n"
        f"memory: {statefulset.memory}"
    )


def render_service_details(service: ServiceSummary) -> str:
    return (
        "service\n"
        f"name: {service.name}\n"
        f"type: {service.type}\n"
        f"cluster-ip: {service.cluster_ip}\n"
        f"ports: {service.ports}\n"
        f"age: {service.age}\n"
        f"selector: {service.selector}"
    )


def render_pvc_details(pvc: PvcSummary) -> str:
    return (
        "pvc\n"
        f"name: {pvc.name}\n"
        f"status: {pvc.status}\n"
        f"volume: {pvc.volume}\n"
        f"capacity: {pvc.capacity}\n"
        f"access: {pvc.access}\n"
        f"storage-class: {pvc.storage_class}\n"
        f"age: {pvc.age}"
    )


def render_namespace_details(namespace: NamespaceSummary) -> str:
    return (
        "namespace\n"
        f"name: {namespace.name}\n"
        f"status: {namespace.status}\n"
        f"age: {namespace.age}\n"
        f"current: {namespace.current or 'no'}"
    )


def render_context_details(context: ContextSummary) -> str:
    return (
        "context\n"
        f"name: {context.name}\n"
        f"cluster: {context.cluster}\n"
        f"user: {context.user}\n"
        f"namespace: {context.namespace}\n"
        f"current: {context.current or 'no'}"
    )


def render_container_details(container: ContainerSummary) -> str:
    return (
        "container\n"
        f"name: {container.name}\n"
        f"pod: {container.pod}\n"
        f"ready: {container.ready}\n"
        f"state: {container.state}\n"
        f"restarts: {container.restarts}\n"
        f"image: {container.image}\n"
        f"cpu: {container.cpu}\n"
        f"memory: {container.memory}"
    )


def render_secret_details(secret: SecretSummary) -> str:
    return (
        "secret\n"
        f"name: {secret.name}\n"
        f"type: {secret.type}\n"
        f"data-items: {secret.data_items}\n"
        f"immutable: {secret.immutable}\n"
        f"age: {secret.age}"
    )
