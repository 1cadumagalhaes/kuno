from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from kubernetes_asyncio.client import CoreV1Api

from kuno.models import PodSummary


class HasCoreV1(Protocol):
    core_v1: CoreV1Api | Any | None


async def list_pods(kube_client: HasCoreV1, namespace: str) -> list[PodSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pod_list = await kube_client.core_v1.list_namespaced_pod(namespace)
    current = datetime.now(UTC)
    return [pod_summary_from_api_item(item, now=current) for item in pod_list.items]


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
