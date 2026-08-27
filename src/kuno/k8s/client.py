from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kubernetes_asyncio.client import ApiClient, AppsV1Api, CoreV1Api, CustomObjectsApi


def _new_client_from_config(*, config_file: str | None, context: str):
    from kubernetes_asyncio.config import new_client_from_config

    return new_client_from_config(config_file=config_file, context=context)


class KubeClient:
    """Asynchronous Kubernetes client.

    Each instance is a lightweight handle over a shared ``ApiClient``. By
    default every ``connect()`` builds a fresh connection (parsing the
    kubeconfig and opening a new aiohttp session), which is expensive when
    done repeatedly on a polling loop. Callers that want to reuse a
    connection across calls should mark the client as ``reuse=True`` (e.g. via
    an app-level pool); the underlying ``ApiClient`` is then cached per
    ``(config_file, context)`` and shared between instances until closed.
    """

    def __init__(self, context: str, config_file: str | None = None) -> None:
        self.context = context
        self.config_file = config_file
        self.api_client: ApiClient | None = None
        self.core_v1: CoreV1Api | None = None
        self.apps_v1: AppsV1Api | None = None
        self.custom_objects: CustomObjectsApi | None = None
        self._reuse = False

    async def connect(self) -> None:
        if self.api_client is not None:
            return
        if self._reuse:
            shared = _shared_clients.get((self.config_file, self.context))
            if shared is not None and shared.api_client is not None:
                self.api_client = shared.api_client
                self.core_v1 = shared.core_v1
                self.apps_v1 = shared.apps_v1
                self.custom_objects = shared.custom_objects
                return
        from kubernetes_asyncio.client import AppsV1Api, CoreV1Api, CustomObjectsApi

        api_client = await _new_client_from_config(
            config_file=self.config_file,
            context=self.context,
        )
        self.api_client = api_client
        self.core_v1 = CoreV1Api(api_client)
        self.apps_v1 = AppsV1Api(api_client)
        self.custom_objects = CustomObjectsApi(api_client)
        if self._reuse:
            _shared_clients[(self.config_file, self.context)] = self

    async def close(self) -> None:
        if self._reuse:
            # A reused client must not tear down the shared connection that
            # other clients rely on; only release this instance's references.
            self.api_client = None
            self.core_v1 = None
            self.apps_v1 = None
            self.custom_objects = None
            return
        if self.api_client is None:
            return

        await self.api_client.close()
        self.api_client = None
        self.core_v1 = None
        self.apps_v1 = None
        self.custom_objects = None

    async def __aenter__(self) -> KubeClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


_shared_clients: dict[tuple[str | None, str], KubeClient] = {}


async def close_all_shared_clients() -> None:
    """Close and evict every cached shared connection (used on app shutdown)."""
    for key, client in list(_shared_clients.items()):
        try:
            if client.api_client is not None:
                await client.api_client.close()
        except Exception:  # noqa: S110
            pass
        del _shared_clients[key]
