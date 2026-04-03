from __future__ import annotations

from datetime import UTC, datetime
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


def render_pod_details(pod: PodSummary) -> str:
    return (
        "pod\n"
        f"name: {pod.name}\n"
        f"ready: {pod.ready}\n"
        f"status: {pod.status}\n"
        f"restarts: {pod.restarts}\n"
        f"age: {pod.age}"
    )
