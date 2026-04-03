from types import SimpleNamespace

import pytest

from kuno.k8s.resources import (
    list_pods,
    pod_summary_from_api_item,
    render_pod_details,
    render_pod_row,
)
from kuno.models import PodSummary


def test_pod_summary_from_api_item_reads_name_and_phase() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        status=SimpleNamespace(phase="Running"),
    )

    assert pod_summary_from_api_item(item) == PodSummary(name="api-1", phase="Running")


def test_pod_summary_from_api_item_defaults_phase() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        status=SimpleNamespace(phase=None),
    )

    assert pod_summary_from_api_item(item) == PodSummary(name="api-1", phase="Unknown")


def test_render_pod_row_formats_summary() -> None:
    assert render_pod_row(PodSummary(name="api-1", phase="Running")) == "api-1 [Running]"


def test_render_pod_details_formats_pod() -> None:
    assert (
        render_pod_details(PodSummary(name="api-1", phase="Running"))
        == "pod\nname: api-1\nphase: Running"
    )


@pytest.mark.asyncio
async def test_list_pods_requires_connected_client() -> None:
    kube_client = SimpleNamespace(core_v1=None)

    with pytest.raises(RuntimeError):
        await list_pods(kube_client, "payments")


@pytest.mark.asyncio
async def test_list_pods_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="api-1"), status=SimpleNamespace(phase="Running")
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="worker-1"), status=SimpleNamespace(phase="Pending")
        ),
    ]

    class FakeCoreV1:
        async def list_namespaced_pod(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_pods(kube_client, "payments") == [
        PodSummary(name="api-1", phase="Running"),
        PodSummary(name="worker-1", phase="Pending"),
    ]
