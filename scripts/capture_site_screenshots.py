"""Capture isolated, fixture-backed Kuno screens for the project landing page."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from kuno.app import EventsScreen, KunoApp, LogsScreen, ManifestScreen
from kuno.config import KunoConfig
from kuno.log_view import LogView
from kuno.models import EventSummary, PodSource, PodSummary, StartupConfig

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "site" / "assets" / "screens"

PODS = [
    PodSummary("storefront-7d9f", "1/1", "Running", 0, "12m", "web", "24m", "48Mi"),
    PodSummary("catalog-55bd", "1/1", "Running", 0, "18m", "api", "31m", "72Mi"),
    PodSummary("checkout-2a10", "1/1", "Running", 1, "24m", "api", "42m", "96Mi"),
    PodSummary("worker-6f83", "1/1", "Running", 0, "31m", "jobs", "18m", "40Mi"),
]

LOGS = """2026-11-19T14:31:02Z {"level":"info","logger":"catalog","message":"cache hit","namespace":"storefront","ttl":60}
[web] 2026-11-19T14:31:03Z {"level":"warning","msg":"slow upstream","duration_ms":812,"route":"/products"}
2026-11-19T14:31:05Z INFO  health check passed
2026-11-19T14:31:08Z {"level":"error","logger":"checkout","message":"payment declined","order":"A-1932","code":"card_declined"}
2026-11-19T14:31:11Z {"level":"debug","component":"pool","message":"connection ready","size":8}
"""

MANIFEST = """apiVersion: v1
kind: Pod
metadata:
  name: storefront-7d9f
  namespace: storefront
  labels:
    app: storefront
    tier: frontend
spec:
  containers:
    - name: web
      image: example.invalid/storefront:1.4.2
      ports:
        - containerPort: 8080
status:
  phase: Running
"""

EVENTS = [
    EventSummary(
        "evt-1",
        "Normal",
        "Scheduled",
        "Successfully assigned storefront/storefront-7d9f to node-a",
        "2m",
        "Pod",
        "storefront-7d9f",
        1,
    ),
    EventSummary(
        "evt-2",
        "Normal",
        "Pulled",
        "Container image already present on machine",
        "2m",
        "Pod",
        "storefront-7d9f",
        1,
    ),
    EventSummary(
        "evt-3", "Normal", "Started", "Started container web", "2m", "Pod", "storefront-7d9f", 1
    ),
    EventSummary(
        "evt-4",
        "Warning",
        "BackOff",
        "Back-off restarting failed container api",
        "8m",
        "Pod",
        "checkout-2a10",
        2,
    ),
]


class FakeClient:
    def __init__(self, context: str) -> None:
        self.context = context

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


async def list_namespaces(*args: object) -> list[str]:
    return ["storefront"]


async def list_pods(*args: object) -> list[PodSummary]:
    return PODS


async def read_logs(*args: object, **kwargs: object) -> str:
    return LOGS


def patches() -> ExitStack:
    stack = ExitStack()
    stack.enter_context(
        patch("kuno.app.load_available_context_names", return_value=["demo-cluster"])
    )
    stack.enter_context(patch("kuno.app.load_startup_targets", side_effect=lambda config: config))
    stack.enter_context(patch("kuno.app.KubeClient", FakeClient))
    stack.enter_context(patch("kuno.app.list_namespaces", new=list_namespaces))
    stack.enter_context(patch("kuno.app.list_pods", new=list_pods))
    stack.enter_context(patch("kuno.app.read_pod_logs", new=read_logs))
    stack.enter_context(patch.object(LogsScreen, "_start_streaming", lambda self: None))
    stack.enter_context(patch("kuno.app.save_config", lambda config: None))
    return stack


async def capture() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = KunoConfig(path=ROOT / "site" / ".demo-config.toml", theme="nord")
    app = KunoApp(
        StartupConfig(context="demo-cluster", namespace="storefront"), config, show_splash=False
    )

    with patches():
        async with app.run_test(size=(118, 36)) as pilot:
            await pilot.pause(0.2)
            app.save_screenshot(OUTPUT / "pods.svg")

            app.action_toggle_info()
            await pilot.pause()
            app.save_screenshot(OUTPUT / "pod-details.svg")

            app.push_screen(
                ManifestScreen(yaml_content=MANIFEST, resource_name="pod/storefront-7d9f")
            )
            await pilot.pause(0.2)
            app.save_screenshot(OUTPUT / "manifest.svg")
            await pilot.press("escape")
            await pilot.pause()

            app.push_screen(EventsScreen(events=EVENTS, title="Events — storefront"))
            await pilot.pause(0.2)
            app.save_screenshot(OUTPUT / "events.svg")
            await pilot.press("escape")
            await pilot.pause()

            app.push_screen(
                LogsScreen(
                    context="demo-cluster",
                    namespace="storefront",
                    logs_source=PodSource(pod_name="storefront-7d9f", container_name="web"),
                    kuno_config=config,
                )
            )
            await pilot.pause(0.3)
            # Park both captures at the top of the buffer so the site can crop raw and pretty
            # to the same rows; following would scroll wrapped JSON out of frame.
            app.screen.query_one("#logs-output", LogView).scroll_home(animate=False)
            await pilot.pause(0.2)
            app.save_screenshot(OUTPUT / "logs-raw.svg")
            app.screen.action_cycle_mode()
            await pilot.pause(0.3)
            app.screen.query_one("#logs-output", LogView).scroll_home(animate=False)
            await pilot.pause(0.2)
            app.save_screenshot(OUTPUT / "logs-pretty.svg")


if __name__ == "__main__":
    asyncio.run(capture())
