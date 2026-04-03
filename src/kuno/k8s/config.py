from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from kubernetes_asyncio.config import list_kube_config_contexts

from kuno.models import ContextSummary, StartupConfig

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


def load_context_summaries(config_file: str | None = None) -> list[ContextSummary]:
    contexts, current_context = list_kube_config_contexts(config_file=config_file)
    current_name = context_name(current_context) if current_context is not None else None
    summaries = [context_summary(context, current_name=current_name) for context in contexts]
    return sorted(summaries, key=lambda summary: summary.name)


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


def context_summary(context: ContextEntry, *, current_name: str | None) -> ContextSummary:
    data = context.get("context", {})
    if not isinstance(data, Mapping):
        data = {}
    name = context_name(context)
    return ContextSummary(
        name=name,
        cluster=_string_or_default(data.get("cluster"), "-"),
        user=_string_or_default(data.get("user"), "-"),
        namespace=_string_or_default(data.get("namespace"), DEFAULT_NAMESPACE),
        current="*" if current_name == name else "",
    )


def _string_or_default(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
