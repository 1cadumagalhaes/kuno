from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from kuno.models import ExplorerView


async def delete_resource(
    kube_client: Any,
    *,
    view: ExplorerView,
    name: str,
    namespace: str,
) -> None:
    if kube_client.core_v1 is None or kube_client.apps_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    if view is ExplorerView.PODS:
        await kube_client.core_v1.delete_namespaced_pod(name, namespace)
        return
    if view is ExplorerView.DEPLOYMENTS:
        await kube_client.apps_v1.delete_namespaced_deployment(name, namespace)
        return
    if view is ExplorerView.STATEFULSETS:
        await kube_client.apps_v1.delete_namespaced_stateful_set(name, namespace)
        return
    if view is ExplorerView.SERVICES:
        await kube_client.core_v1.delete_namespaced_service(name, namespace)
        return
    if view is ExplorerView.PVC:
        await kube_client.core_v1.delete_namespaced_persistent_volume_claim(name, namespace)
        return
    if view is ExplorerView.SECRETS:
        await kube_client.core_v1.delete_namespaced_secret(name, namespace)
        return

    raise ValueError(f"Delete is not supported for {view.value}")


async def list_pods_to_clear(
    kube_client: Any,
    namespace: str,
    *,
    statuses: set[str],
) -> list[str]:
    """Return the names of pods in *namespace* matching one of the given
    terminal statuses (Failed, Succeeded, Evicted, ...)."""
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    pod_list = await kube_client.core_v1.list_namespaced_pod(namespace)
    matches: list[str] = []
    for pod in pod_list.items:
        metadata = getattr(pod, "metadata", None)
        status = getattr(pod, "status", None)
        name = getattr(metadata, "name", None)
        phase = getattr(status, "phase", None)
        reason = getattr(status, "reason", None)
        if not isinstance(name, str) or not name:
            continue
        actual = reason if isinstance(reason, str) and reason else phase
        if isinstance(actual, str) and actual in statuses:
            matches.append(name)
    return matches


async def delete_pods(
    kube_client: Any,
    namespace: str,
    names: list[str],
) -> int:
    """Delete the given pods, returning how many were deleted."""
    if kube_client.core_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    deleted = 0
    for name in names:
        try:
            await kube_client.core_v1.delete_namespaced_pod(name, namespace)
            deleted += 1
        except Exception:  # noqa: S112 - per-pod delete failures are non-fatal
            continue
    return deleted


async def restart_resource(
    kube_client: Any,
    *,
    view: ExplorerView,
    name: str,
    namespace: str,
) -> None:
    if kube_client.apps_v1 is None:
        raise RuntimeError("Kubernetes client is not connected")

    body = rollout_restart_patch()
    if view is ExplorerView.DEPLOYMENTS:
        await kube_client.apps_v1.patch_namespaced_deployment(name, namespace, body)
        return
    if view is ExplorerView.STATEFULSETS:
        await kube_client.apps_v1.patch_namespaced_stateful_set(name, namespace, body)
        return

    raise ValueError(f"Restart is not supported for {view.value}")


def rollout_restart_patch(now: datetime | None = None) -> dict[str, Any]:
    timestamp = (now or datetime.now(UTC)).isoformat()
    return {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": timestamp,
                    }
                }
            }
        }
    }
