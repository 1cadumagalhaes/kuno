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
