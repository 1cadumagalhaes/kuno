from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from kubernetes_asyncio.client import CoreV1Api

from kuno.models import PodSummary


class HasCoreV1(Protocol):
    core_v1: CoreV1Api | Any | None


async def list_pods(kube_client: HasCoreV1, namespace: str) -> list[PodSummary]:
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pod_list = await kube_client.core_v1.list_namespaced_pod(namespace)
    return [pod_summary_from_api_item(item) for item in pod_list.items]


def pod_summary_from_api_item(item: Any) -> PodSummary:
    metadata = getattr(item, "metadata", None)
    status = getattr(item, "status", None)
    name = getattr(metadata, "name", None)
    phase = getattr(status, "phase", None)

    if not isinstance(name, str) or not name:
        raise ValueError("Pod is missing a valid name")

    if not isinstance(phase, str) or not phase:
        phase = "Unknown"

    return PodSummary(name=name, phase=phase)


def render_pod_summaries(pods: Sequence[PodSummary]) -> str:
    if not pods:
        return "pods\n(no pods found)"

    rows = ["pods"]
    rows.extend(f"{pod.name} [{pod.phase}]" for pod in pods)
    return "\n".join(rows)
