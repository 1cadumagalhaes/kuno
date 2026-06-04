from __future__ import annotations

from kubernetes_asyncio.client import ApiClient, AppsV1Api, CoreV1Api, CustomObjectsApi
from kubernetes_asyncio.config import new_client_from_config


class KubeClient:
    def __init__(self, context: str, config_file: str | None = None) -> None:
        self.context = context
        self.config_file = config_file
        self.api_client: ApiClient | None = None
        self.core_v1: CoreV1Api | None = None
        self.apps_v1: AppsV1Api | None = None
        self.custom_objects: CustomObjectsApi | None = None

    async def connect(self) -> None:
        api_client = await new_client_from_config(
            config_file=self.config_file,
            context=self.context,
        )
        self.api_client = api_client
        self.core_v1 = CoreV1Api(api_client)
        self.apps_v1 = AppsV1Api(api_client)
        self.custom_objects = CustomObjectsApi(api_client)

    async def close(self) -> None:
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
