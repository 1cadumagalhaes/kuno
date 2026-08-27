from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from kuno.k8s.actions import (
    delete_pods,
    delete_resource,
    list_pods_to_clear,
    restart_resource,
    rollout_restart_patch,
)
from kuno.models import ExplorerView


def test_rollout_restart_patch_sets_annotation() -> None:
    patch = rollout_restart_patch(now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC))

    assert patch == {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": "2026-04-02T12:00:00+00:00"
                    }
                }
            }
        }
    }


@pytest.mark.asyncio
async def test_delete_resource_deletes_supported_views() -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeCoreV1:
        async def delete_namespaced_pod(self, name: str, namespace: str) -> None:
            calls.append(("pod", name, namespace))

        async def delete_namespaced_service(self, name: str, namespace: str) -> None:
            calls.append(("service", name, namespace))

        async def delete_namespaced_persistent_volume_claim(
            self, name: str, namespace: str
        ) -> None:
            calls.append(("pvc", name, namespace))

        async def delete_namespaced_secret(self, name: str, namespace: str) -> None:
            calls.append(("secret", name, namespace))

    class FakeAppsV1:
        async def delete_namespaced_deployment(self, name: str, namespace: str) -> None:
            calls.append(("deployment", name, namespace))

        async def delete_namespaced_stateful_set(self, name: str, namespace: str) -> None:
            calls.append(("statefulset", name, namespace))

    kube_client = SimpleNamespace(core_v1=FakeCoreV1(), apps_v1=FakeAppsV1())

    await delete_resource(kube_client, view=ExplorerView.PODS, name="api-1", namespace="payments")
    await delete_resource(
        kube_client, view=ExplorerView.DEPLOYMENTS, name="api", namespace="payments"
    )
    await delete_resource(
        kube_client, view=ExplorerView.STATEFULSETS, name="postgres", namespace="payments"
    )
    await delete_resource(kube_client, view=ExplorerView.SERVICES, name="api", namespace="payments")
    await delete_resource(kube_client, view=ExplorerView.PVC, name="data", namespace="payments")
    await delete_resource(
        kube_client, view=ExplorerView.SECRETS, name="app-secrets", namespace="payments"
    )

    assert calls == [
        ("pod", "api-1", "payments"),
        ("deployment", "api", "payments"),
        ("statefulset", "postgres", "payments"),
        ("service", "api", "payments"),
        ("pvc", "data", "payments"),
        ("secret", "app-secrets", "payments"),
    ]


@pytest.mark.asyncio
async def test_restart_resource_restarts_supported_views() -> None:
    calls: list[tuple[str, str, str, dict]] = []

    class FakeAppsV1:
        async def patch_namespaced_deployment(self, name: str, namespace: str, body: dict) -> None:
            calls.append(("deployment", name, namespace, body))

        async def patch_namespaced_stateful_set(
            self, name: str, namespace: str, body: dict
        ) -> None:
            calls.append(("statefulset", name, namespace, body))

    kube_client = SimpleNamespace(apps_v1=FakeAppsV1())

    await restart_resource(
        kube_client, view=ExplorerView.DEPLOYMENTS, name="api", namespace="payments"
    )
    await restart_resource(
        kube_client, view=ExplorerView.STATEFULSETS, name="postgres", namespace="payments"
    )

    assert calls[0][0:3] == ("deployment", "api", "payments")
    assert calls[1][0:3] == ("statefulset", "postgres", "payments")
    assert (
        "kubectl.kubernetes.io/restartedAt"
        in calls[0][3]["spec"]["template"]["metadata"]["annotations"]
    )


@pytest.mark.asyncio
async def test_restart_resource_rejects_unsupported_view() -> None:
    kube_client = SimpleNamespace(apps_v1=SimpleNamespace())

    with pytest.raises(ValueError):
        await restart_resource(
            kube_client, view=ExplorerView.PODS, name="api-1", namespace="payments"
        )


@pytest.mark.asyncio
async def test_list_pods_to_clear_filters_by_status() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-fail"),
            status=SimpleNamespace(phase="Failed", reason=None),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-ok"),
            status=SimpleNamespace(phase="Succeeded", reason=None),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-evicted"),
            status=SimpleNamespace(phase="Failed", reason="Evicted"),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="job-running"),
            status=SimpleNamespace(phase="Running", reason=None),
        ),
    ]

    class FakeCoreV1:
        async def list_namespaced_pod(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_pods_to_clear(
        kube_client, "payments", statuses={"Failed", "Succeeded", "Evicted"}
    ) == ["job-fail", "job-ok", "job-evicted"]
    assert await list_pods_to_clear(kube_client, "payments", statuses={"Failed"}) == [
        "job-fail",
    ]


@pytest.mark.asyncio
async def test_delete_pods_deletes_each_pod() -> None:
    deleted: list[str] = []

    class FakeCoreV1:
        async def delete_namespaced_pod(self, name: str, namespace: str) -> None:
            assert namespace == "payments"
            deleted.append(name)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    count = await delete_pods(kube_client, "payments", ["a", "b", "c"])

    assert count == 3
    assert deleted == ["a", "b", "c"]
