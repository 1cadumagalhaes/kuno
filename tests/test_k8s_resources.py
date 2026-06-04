from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from kuno.k8s.resources import (
    container_summaries_from_pod,
    container_summary,
    deployment_summary_from_api_item,
    format_age,
    format_cpu_requests,
    format_memory_requests,
    list_deployments,
    list_namespace_summaries,
    list_namespaces,
    list_pod_containers,
    list_pods,
    list_pvcs,
    list_secrets,
    list_services,
    list_statefulsets,
    namespace_summary_from_api_item,
    parse_since_duration,
    pod_ready,
    pod_restarts,
    pod_summary_from_api_item,
    pvc_summary_from_api_item,
    read_pod_logs,
    render_container_details,
    render_context_details,
    render_namespace_details,
    render_pod_details,
    render_pvc_details,
    render_secret_details,
    render_service_details,
    render_statefulset_details,
    secret_summary_from_api_item,
    service_summary_from_api_item,
    statefulset_summary_from_api_item,
    stream_pod_logs,
    truncate_for_table,
)
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
        cpu="-/750m",
        memory="-/384Mi",
        cpu_requests="750m",
        memory_requests="384Mi",
        created="2024-01-01T11:55:00+00:00",
        container_details=(
            "api",
            "  state: Unknown",
            "  ready: false",
            "  restarts: 0",
            "  image: -",
            "  cpu: - / 250m / -",
            "  memory: - / 128Mi / -",
            "sidecar",
            "  state: Unknown",
            "  ready: false",
            "  restarts: 0",
            "  image: -",
            "  cpu: - / 500m / -",
            "  memory: - / 256Mi / -",
        ),
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


def test_pod_summary_includes_usage_requests_and_limits() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        status=SimpleNamespace(
            phase="Running",
            container_statuses=[SimpleNamespace(name="api", ready=True, restart_count=1)],
        ),
        spec=SimpleNamespace(
            node_name="node-1",
            containers=[
                SimpleNamespace(
                    name="api",
                    image="ghcr.io/acme/api:v1",
                    resources=SimpleNamespace(
                        requests={"cpu": "500m", "memory": "256Mi"},
                        limits={"cpu": "1", "memory": "1Gi"},
                    ),
                )
            ],
        ),
    )

    pod = pod_summary_from_api_item(
        item,
        metrics={"api": {"cpu": "42000000n", "memory": "128Mi"}},
    )

    assert pod.cpu == "42m/500m"
    assert pod.memory == "128Mi/256Mi"
    assert pod.cpu_usage == "42m"
    assert pod.cpu_requests == "500m"
    assert pod.cpu_limits == "1"
    assert pod.memory_usage == "128Mi"
    assert pod.memory_requests == "256Mi"
    assert pod.memory_limits == "1Gi"
    assert pod.node == "node-1"
    assert pod.container_details == (
        "api",
        "  state: Unknown",
        "  ready: true",
        "  restarts: 1",
        "  image: ghcr.io/acme/api:v1",
        "  cpu: 42m / 500m / 1",
        "  memory: 128Mi / 256Mi / 1Gi",
    )


def test_failed_pod_can_show_running_container_state() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="job-1"),
        status=SimpleNamespace(
            phase="Failed",
            container_statuses=[
                SimpleNamespace(
                    name="base",
                    ready=False,
                    restart_count=0,
                    state=SimpleNamespace(
                        running=SimpleNamespace(
                            started_at=datetime(2026, 6, 4, 16, 24, 2, tzinfo=UTC)
                        ),
                        waiting=None,
                        terminated=None,
                    ),
                )
            ],
        ),
        spec=SimpleNamespace(containers=[SimpleNamespace(name="base", image="busybox")]),
    )

    pod = pod_summary_from_api_item(item)

    assert pod.status == "Failed"
    assert pod.container_details[:4] == (
        "base",
        "  state: Running",
        "  started: 2026-06-04T16:24:02+00:00",
        "  ready: false",
    )


def test_terminated_container_details_include_reason_and_exit_code() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(name="job-1"),
        status=SimpleNamespace(
            phase="Failed",
            container_statuses=[
                SimpleNamespace(
                    name="base",
                    ready=False,
                    restart_count=0,
                    state=SimpleNamespace(
                        running=None,
                        waiting=None,
                        terminated=SimpleNamespace(
                            reason="Error",
                            exit_code=1,
                            signal=None,
                            started_at=datetime(2026, 6, 4, 16, 24, 2, tzinfo=UTC),
                            finished_at=datetime(2026, 6, 4, 16, 25, 2, tzinfo=UTC),
                            message="command failed",
                        ),
                    ),
                )
            ],
        ),
        spec=SimpleNamespace(containers=[SimpleNamespace(name="base", image="busybox")]),
    )

    pod = pod_summary_from_api_item(item)

    assert "  state: Terminated" in pod.container_details
    assert "  reason: Error" in pod.container_details
    assert "  exit code: 1" in pod.container_details
    assert "  finished: 2026-06-04T16:25:02+00:00" in pod.container_details
    assert "  message: command failed" in pod.container_details


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
    assert render_pod_details(
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
    ) == "\n".join(
        [
            "pod/api-1",
            "",
            "Status",
            "phase: Running",
            "ready: 1/1",
            "restarts: 2",
            "age: 5m",
            "node: -",
            "pod ip: -",
            "host ip: -",
            "qos: -",
            "priority: -",
            "",
            "Resources",
            "CPU     use -    req -    lim -",
            "Memory  use -    req -    lim -",
            "",
            "Conditions",
            "-",
            "",
            "Ownership",
            "-",
            "",
            "Timestamps",
            "started: -",
            "created: -",
            "",
            "Containers",
            "-",
        ]
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


@pytest.mark.asyncio
async def test_list_namespaces_maps_api_items() -> None:
    items = [
        SimpleNamespace(metadata=SimpleNamespace(name="billing")),
        SimpleNamespace(metadata=SimpleNamespace(name="airflow")),
    ]

    class FakeCoreV1:
        async def list_namespace(self) -> SimpleNamespace:
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_namespaces(kube_client) == ["airflow", "billing"]


def test_deployment_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="api",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        spec=SimpleNamespace(
            replicas=3,
            template=SimpleNamespace(
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
                )
            ),
        ),
        status=SimpleNamespace(ready_replicas=2, updated_replicas=3, available_replicas=2),
    )

    assert deployment_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == DeploymentSummary(
        name="api",
        ready="2/3",
        up_to_date=3,
        available=2,
        age="1h",
        containers="api,sidecar",
        cpu="750m",
        memory="384Mi",
    )


@pytest.mark.asyncio
async def test_list_deployments_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="api"),
            spec=SimpleNamespace(
                replicas=2, template=SimpleNamespace(spec=SimpleNamespace(containers=[]))
            ),
            status=SimpleNamespace(ready_replicas=1, updated_replicas=2, available_replicas=1),
        )
    ]

    class FakeAppsV1:
        async def list_namespaced_deployment(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(apps_v1=FakeAppsV1())

    assert await list_deployments(kube_client, "payments") == [
        DeploymentSummary(
            name="api",
            ready="1/2",
            up_to_date=2,
            available=1,
            age="-",
            containers="-",
            cpu="-",
            memory="-",
        )
    ]


def test_statefulset_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="postgres",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        spec=SimpleNamespace(
            replicas=3,
            template=SimpleNamespace(
                spec=SimpleNamespace(
                    containers=[
                        SimpleNamespace(
                            name="postgres",
                            resources=SimpleNamespace(requests={"cpu": "500m", "memory": "1Gi"}),
                        )
                    ]
                )
            ),
        ),
        status=SimpleNamespace(ready_replicas=2, updated_replicas=2, current_replicas=3),
    )

    assert statefulset_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == StatefulSetSummary(
        name="postgres",
        ready="2/3",
        updated=2,
        current=3,
        age="1h",
        containers="postgres",
        cpu="500m",
        memory="1Gi",
    )


@pytest.mark.asyncio
async def test_list_statefulsets_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="postgres"),
            spec=SimpleNamespace(
                replicas=2, template=SimpleNamespace(spec=SimpleNamespace(containers=[]))
            ),
            status=SimpleNamespace(ready_replicas=1, updated_replicas=2, current_replicas=1),
        )
    ]

    class FakeAppsV1:
        async def list_namespaced_stateful_set(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(apps_v1=FakeAppsV1())

    assert await list_statefulsets(kube_client, "payments") == [
        StatefulSetSummary(
            name="postgres",
            ready="1/2",
            updated=2,
            current=1,
            age="-",
            containers="-",
            cpu="-",
            memory="-",
        )
    ]


def test_render_statefulset_details_formats_statefulset() -> None:
    assert (
        render_statefulset_details(
            StatefulSetSummary(
                name="postgres",
                ready="2/3",
                updated=2,
                current=3,
                age="1h",
                containers="postgres",
                cpu="500m",
                memory="1Gi",
            )
        )
        == "statefulset\nname: postgres\nready: 2/3\nupdated: 2\ncurrent: 3\nage: 1h\ncontainers: postgres\ncpu: 500m\nmemory: 1Gi"
    )


def test_service_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="api",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        spec=SimpleNamespace(
            type="ClusterIP",
            cluster_ip="10.0.0.1",
            ports=[
                SimpleNamespace(port=80, protocol="TCP"),
                SimpleNamespace(port=443, protocol="TCP"),
            ],
            selector={"app": "api", "tier": "backend"},
        ),
    )

    assert service_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == ServiceSummary(
        name="api",
        type="ClusterIP",
        cluster_ip="10.0.0.1",
        ports="80/TCP,443/TCP",
        age="1h",
        selector="app=api,tier=backend",
    )


@pytest.mark.asyncio
async def test_list_services_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="api"),
            spec=SimpleNamespace(type="ClusterIP", cluster_ip="10.0.0.1", ports=[], selector=None),
        )
    ]

    class FakeCoreV1:
        async def list_namespaced_service(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_services(kube_client, "payments") == [
        ServiceSummary(
            name="api",
            type="ClusterIP",
            cluster_ip="10.0.0.1",
            ports="-",
            age="-",
            selector="-",
        )
    ]


def test_render_service_details_formats_service() -> None:
    assert (
        render_service_details(
            ServiceSummary(
                name="api",
                type="ClusterIP",
                cluster_ip="10.0.0.1",
                ports="80/TCP,443/TCP",
                age="1h",
                selector="app=api,tier=backend",
            )
        )
        == "service\nname: api\ntype: ClusterIP\ncluster-ip: 10.0.0.1\nports: 80/TCP,443/TCP\nage: 1h\nselector: app=api,tier=backend"
    )


def test_pvc_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="data-postgres-0",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        spec=SimpleNamespace(
            volume_name="pvc-123",
            access_modes=["ReadWriteOnce"],
            storage_class_name="fast-ssd",
        ),
        status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
    )

    assert pvc_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == PvcSummary(
        name="data-postgres-0",
        status="Bound",
        volume="pvc-123",
        capacity="10Gi",
        access="ReadWriteOnce",
        storage_class="fast-ssd",
        age="1h",
    )


@pytest.mark.asyncio
async def test_list_pvcs_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="data-postgres-0"),
            spec=SimpleNamespace(
                volume_name="pvc-123",
                access_modes=["ReadWriteOnce"],
                storage_class_name="fast-ssd",
            ),
            status=SimpleNamespace(phase="Bound", capacity={"storage": "10Gi"}),
        )
    ]

    class FakeCoreV1:
        async def list_namespaced_persistent_volume_claim(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_pvcs(kube_client, "payments") == [
        PvcSummary(
            name="data-postgres-0",
            status="Bound",
            volume="pvc-123",
            capacity="10Gi",
            access="ReadWriteOnce",
            storage_class="fast-ssd",
            age="-",
        )
    ]


def test_render_pvc_details_formats_pvc() -> None:
    assert (
        render_pvc_details(
            PvcSummary(
                name="data-postgres-0",
                status="Bound",
                volume="pvc-123",
                capacity="10Gi",
                access="ReadWriteOnce",
                storage_class="fast-ssd",
                age="1h",
            )
        )
        == "pvc\nname: data-postgres-0\nstatus: Bound\nvolume: pvc-123\ncapacity: 10Gi\naccess: ReadWriteOnce\nstorage-class: fast-ssd\nage: 1h"
    )


def test_secret_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="app-secrets",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        type="Opaque",
        data={"DATABASE_URL": "...", "API_KEY": "..."},
        immutable=True,
    )

    assert secret_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    ) == SecretSummary(
        name="app-secrets",
        type="Opaque",
        data_items=2,
        immutable="yes",
        age="1h",
    )


@pytest.mark.asyncio
async def test_list_secrets_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="app-secrets"),
            type="Opaque",
            data={"DATABASE_URL": "..."},
            immutable=False,
        )
    ]

    class FakeCoreV1:
        async def list_namespaced_secret(self, namespace: str) -> SimpleNamespace:
            assert namespace == "payments"
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_secrets(kube_client, "payments") == [
        SecretSummary(
            name="app-secrets",
            type="Opaque",
            data_items=1,
            immutable="no",
            age="-",
        )
    ]


def test_render_secret_details_formats_secret() -> None:
    assert (
        render_secret_details(
            SecretSummary(
                name="app-secrets",
                type="Opaque",
                data_items=2,
                immutable="yes",
                age="1h",
            )
        )
        == "secret\nname: app-secrets\ntype: Opaque\ndata-items: 2\nimmutable: yes\nage: 1h"
    )


def test_namespace_summary_from_api_item_reads_operational_fields() -> None:
    item = SimpleNamespace(
        metadata=SimpleNamespace(
            name="airflow",
            creation_timestamp=datetime(2026, 4, 2, 11, 0, tzinfo=UTC),
        ),
        status=SimpleNamespace(phase="Active"),
    )

    assert namespace_summary_from_api_item(
        item, now=datetime(2026, 4, 2, 12, 0, tzinfo=UTC), current_namespace="airflow"
    ) == NamespaceSummary(name="airflow", status="Active", age="1h", current="*")


@pytest.mark.asyncio
async def test_list_namespace_summaries_maps_api_items() -> None:
    items = [
        SimpleNamespace(
            metadata=SimpleNamespace(name="airflow"), status=SimpleNamespace(phase="Active")
        ),
        SimpleNamespace(
            metadata=SimpleNamespace(name="billing"), status=SimpleNamespace(phase="Active")
        ),
    ]

    class FakeCoreV1:
        async def list_namespace(self) -> SimpleNamespace:
            return SimpleNamespace(items=items)

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_namespace_summaries(kube_client, current_namespace="billing") == [
        NamespaceSummary(name="airflow", status="Active", age="-", current=""),
        NamespaceSummary(name="billing", status="Active", age="-", current="*"),
    ]


def test_render_namespace_details_formats_namespace() -> None:
    assert (
        render_namespace_details(
            NamespaceSummary(name="airflow", status="Active", age="1h", current="*")
        )
        == "namespace\nname: airflow\nstatus: Active\nage: 1h\ncurrent: *"
    )


def test_render_context_details_formats_context() -> None:
    assert (
        render_context_details(
            ContextSummary(
                name="prod",
                cluster="prod-cluster",
                user="prod-user",
                namespace="airflow",
                current="*",
            )
        )
        == "context\nname: prod\ncluster: prod-cluster\nuser: prod-user\nnamespace: airflow\ncurrent: *"
    )


def test_container_summaries_from_pod_reads_operational_fields() -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(
                    name="api",
                    image="ghcr.io/example/api:1.0.0",
                    resources=SimpleNamespace(requests={"cpu": "250m", "memory": "128Mi"}),
                ),
                SimpleNamespace(
                    name="sidecar",
                    image="ghcr.io/example/sidecar:1.0.0",
                    resources=SimpleNamespace(requests={"cpu": "100m", "memory": "64Mi"}),
                ),
            ]
        ),
        status=SimpleNamespace(
            container_statuses=[
                SimpleNamespace(
                    name="api",
                    ready=True,
                    restart_count=1,
                    state=SimpleNamespace(running=SimpleNamespace()),
                ),
                SimpleNamespace(
                    name="sidecar",
                    ready=False,
                    restart_count=0,
                    state=SimpleNamespace(waiting=SimpleNamespace()),
                ),
            ]
        ),
    )

    assert container_summaries_from_pod(pod) == [
        ContainerSummary(
            name="api",
            pod="api-1",
            ready="yes",
            state="Running",
            restarts=1,
            image="ghcr.io/example/api:1.0.0",
            cpu="250m",
            memory="128Mi",
        ),
        ContainerSummary(
            name="sidecar",
            pod="api-1",
            ready="no",
            state="Waiting",
            restarts=0,
            image="ghcr.io/example/sidecar:1.0.0",
            cpu="100m",
            memory="64Mi",
        ),
    ]


@pytest.mark.asyncio
async def test_list_pod_containers_reads_selected_pod() -> None:
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="api-1"),
        spec=SimpleNamespace(
            containers=[
                SimpleNamespace(
                    name="api",
                    image="ghcr.io/example/api:1.0.0",
                    resources=SimpleNamespace(requests={}),
                )
            ]
        ),
        status=SimpleNamespace(
            container_statuses=[
                SimpleNamespace(
                    name="api",
                    ready=True,
                    restart_count=0,
                    state=SimpleNamespace(running=SimpleNamespace()),
                )
            ]
        ),
    )

    class FakeCoreV1:
        async def read_namespaced_pod(self, name: str, namespace: str) -> SimpleNamespace:
            assert name == "api-1"
            assert namespace == "payments"
            return pod

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert await list_pod_containers(kube_client, "payments", "api-1") == [
        ContainerSummary(
            name="api",
            pod="api-1",
            ready="yes",
            state="Running",
            restarts=0,
            image="ghcr.io/example/api:1.0.0",
            cpu="-",
            memory="-",
        )
    ]


def test_render_container_details_formats_container() -> None:
    assert (
        render_container_details(
            ContainerSummary(
                name="api",
                pod="api-1",
                ready="yes",
                state="Running",
                restarts=1,
                image="ghcr.io/example/api:1.0.0",
                cpu="250m",
                memory="128Mi",
            )
        )
        == "container\nname: api\npod: api-1\nready: yes\nstate: Running\nrestarts: 1\nimage: ghcr.io/example/api:1.0.0\ncpu: 250m\nmemory: 128Mi"
    )


@pytest.mark.asyncio
async def test_read_pod_logs_reads_selected_pod_and_container() -> None:
    class FakeCoreV1:
        async def read_namespaced_pod_log(self, name: str, namespace: str, **kwargs) -> str:
            assert name == "api-1"
            assert namespace == "payments"
            assert kwargs == {"tail_lines": 500, "timestamps": False, "container": "api"}
            return "line-1\nline-2"

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    assert (
        await read_pod_logs(kube_client, "payments", "api-1", container_name="api")
        == "line-1\nline-2"
    )


@pytest.mark.asyncio
async def test_stream_pod_logs_yields_lines() -> None:
    class FakeContent:
        def __init__(self) -> None:
            self.lines = [b"line-1\n", b"line-2\n", b""]

        async def readline(self) -> bytes:
            return self.lines.pop(0)

    class FakeResponse:
        def __init__(self) -> None:
            self.content = FakeContent()
            self.closed = False

        def close(self) -> None:
            self.closed = True

    response = FakeResponse()

    class FakeCoreV1:
        async def read_namespaced_pod_log(self, name: str, namespace: str, **kwargs):
            assert name == "api-1"
            assert namespace == "payments"
            assert kwargs["follow"] is True
            assert kwargs["_preload_content"] is False
            return response

    kube_client = SimpleNamespace(core_v1=FakeCoreV1())

    lines = [
        line
        async for line in stream_pod_logs(kube_client, "payments", "api-1", container_name="api")
    ]

    assert lines == ["line-1", "line-2"]
    assert response.closed is True


def test_parse_since_duration_supports_kubectl_style_values() -> None:
    assert parse_since_duration("") is None
    assert parse_since_duration("30s") == 30
    assert parse_since_duration("5m") == 300
    assert parse_since_duration("2h") == 7200
    assert parse_since_duration("1d") == 86400
