from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from kubernetes_asyncio.config import list_kube_config_contexts

from kuno.models import StartupConfig

DEFAULT_NAMESPACE = "default"

ContextEntry = Mapping[str, Any]


class UnknownContextError(ValueError):
    pass


def load_startup_targets(
    startup_config: StartupConfig,
    config_file: str | None = None,
) -> StartupConfig:
    contexts, current_context = list_kube_config_contexts(config_file=config_file)
    return resolve_startup_targets(startup_config, contexts, current_context)


def load_available_context_names(config_file: str | None = None) -> list[str]:
    contexts, _ = list_kube_config_contexts(config_file=config_file)
    return sorted(context_name(context) for context in contexts)


def resolve_startup_targets(
    startup_config: StartupConfig,
    contexts: Sequence[ContextEntry],
    current_context: ContextEntry | None,
) -> StartupConfig:
    selected_context = resolve_context_name(startup_config, contexts, current_context)
    selected_namespace = resolve_namespace_name(startup_config, contexts, selected_context)
    return StartupConfig(context=selected_context, namespace=selected_namespace)


def resolve_context_name(
    startup_config: StartupConfig,
    contexts: Sequence[ContextEntry],
    current_context: ContextEntry | None,
) -> str:
    available_contexts = {context_name(context) for context in contexts}
    if startup_config.context is not None:
        if startup_config.context not in available_contexts:
            raise UnknownContextError(startup_config.context)
        return startup_config.context

    if current_context is None:
        raise UnknownContextError("No kubeconfig context is available")

    return context_name(current_context)


def resolve_namespace_name(
    startup_config: StartupConfig,
    contexts: Sequence[ContextEntry],
    selected_context: str,
) -> str:
    if startup_config.namespace is not None:
        return startup_config.namespace

    selected_context_entry = next(
        context for context in contexts if context_name(context) == selected_context
    )
    context_namespace = selected_context_entry.get("context", {}).get("namespace")
    if isinstance(context_namespace, str) and context_namespace:
        return context_namespace
    return DEFAULT_NAMESPACE


def context_name(context: ContextEntry) -> str:
    name = context.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("Kubeconfig context is missing a valid name")
    return name
