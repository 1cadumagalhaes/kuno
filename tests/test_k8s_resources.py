from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from kuno.k8s.resources import (
    container_summary,
    format_age,
    format_cpu_requests,
    format_memory_requests,
    list_pods,
    pod_ready,
    pod_restarts,
    pod_summary_from_api_item,
    render_pod_details,
    truncate_for_table,
)
from kuno.models import PodSummary


def test_pod_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="api-1",
            creation_timestamp=datetime(2024, 1, 1, 11, 55, tzinfo=UTC),
        ),
        status=SimpleNamespace(
            phase="Running",
            reason=None,
            container_statuses=[
                SimpleNamespace(ready=True, restart_count=1),
                SimpleNamespace(ready=False, restart_count=2),
            ],
        ),
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(
                    name="api",
                    resources=SimpleNamespace(requests={"cpu": "250m", "memory": "128Mi"}),
                ),
                SimpleNamespace(
                    name="sidecar",
                    resources=SimpleNamespace(requests={"cpu": "500m", "memory": "256Mi"}),
                ),
            ]
        ),
    )

    assert pod_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == PodSummary(
        name="api-1",
        ready="1/2",
        status="Running",
        restarts=3,
        age="822d",
        containers="api,sidecar",
        cpu="750m",
        memory="384Mi",
    )


def test_pod_summary_from_api_item_defaults_phase() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        status=SimpleNamespace(phase=None),
    )

    assert pod_summary_from_api_item(item) == PodSummary(
        name="api-1",
        ready="0/0",
        status="Unknown",
        restarts=0,
        age="-",
        containers="-",
        cpu="-",
        memory="-",
    )


def test_container_summary_formats_names() -> None:
    assert container_summary([SimpleNamespace(name="api")]) == "api"
    assert (
        container_summary([SimpleNamespace(name="api"), SimpleNamespace(name="sidecar")])
        == "api,sidecar"
    )


def test_truncate_for_table_limits_long_values() -> None:
    assert truncate_for_table("short", max_length=8) == "short"
    assert truncate_for_table("very-long-name", max_length=8) == "very-..."
    assert (
        container_summary(
            [
                SimpleNamespace(name="api"),
                SimpleNamespace(name="sidecar"),
                SimpleNamespace(name="metrics"),
            ]
        )
        == "api,+2"
    )


def test_pod_ready_counts_ready_containers() -> None:
    container_statuses = [
        SimpleNamespace(ready=True, restart_count=1),
        SimpleNamespace(ready=False, restart_count=2),
    ]

    assert pod_ready(container_statuses) == "1/2"


def test_pod_restarts_sums_restart_counts() -> None:
    container_statuses = [
        SimpleNamespace(ready=True, restart_count=1),
        SimpleNamespace(ready=False, restart_count=2),
    ]

    assert pod_restarts(container_statuses) == 3


def test_format_age_formats_ranges() -> None:
    now = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)

    assert format_age(datetime(2026, 4, 2, 11, 59, 30, tzinfo=UTC), now=now) == "30s"
    assert format_age(datetime(2026, 4, 2, 11, 30, tzinfo=UTC), now=now) == "30m"
    assert format_age(datetime(2026, 4, 2, 7, 0, tzinfo=UTC), now=now) == "5h"
    assert format_age(datetime(2026, 3, 30, 12, 0, tzinfo=UTC), now=now) == "3d"


def test_format_cpu_requests_sums_container_requests() -> None:
    containers = [
        SimpleNamespace(resources=SimpleNamespace(requests={"cpu": "250m"})),
        SimpleNamespace(resources=SimpleNamespace(requests={"cpu": "500m"})),
    ]

    assert format_cpu_requests(containers) == "750m"


def test_format_memory_requests_sums_container_requests() -> None:
    containers = [
        SimpleNamespace(resources=SimpleNamespace(requests={"memory": "128Mi"})),
        SimpleNamespace(resources=SimpleNamespace(requests={"memory": "256Mi"})),
    ]

    assert format_memory_requests(containers) == "384Mi"


def test_render_pod_details_formats_pod() -> None:
    assert (
        render_pod_details(
            PodSummary(
                name="api-1",
                ready="1/1",
                status="Running",
                restarts=2,
                age="5m",
                containers="api,sidecar",
                cpu="500m",
                memory="256Mi",
            )
        )
        == "pod\nname: api-1\nready: 1/1\nstatus: Running\nrestarts: 2\nage: 5m\ncontainers: api,sidecar\ncpu: 500m\nmemory: 256Mi"
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
            metadata=SimpleNamespace(name="api-1"),
            status=SimpleNamespace(phase="Running"),
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="worker-1"),
            status=SimpleNamespace(phase="Pending"),
        ),
    ]

    class FakeCoreV1:
        async def list_namespaced_pod(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_pods(kube_client, "payments") == [
        PodSummary(
            name="api-1",
            ready="0/0",
            status="Running",
            restarts=0,
            age="-",
            containers="-",
            cpu="-",
            memory="-",
        ),
        PodSummary(
            name="worker-1",
            ready="0/0",
            status="Pending",
            restarts=0,
            age="-",
            containers="-",
            cpu="-",
            memory="-",
        ),
    ]
