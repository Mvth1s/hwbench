import platform
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

TData = TypeVar("TData")
TIds = TypeVar("TIds")


@dataclass(frozen=True)
class ComponentResult(Generic[TData, TIds]):
    data: TData
    identifiers: TIds | None = None


class Collector(ABC, Generic[TData, TIds]):
    component: ClassVar[str]

    @abstractmethod
    def collect(self, include_identifiers: bool = False) -> ComponentResult[TData, TIds]:
        """Ne lit aucun identifiant matériel tant que include_identifiers est False."""


class UnsupportedPlatformError(RuntimeError):
    pass


_REGISTRY: dict[str, dict[str, type[Collector[Any, Any]]]] = {}

C = TypeVar("C", bound=type[Collector[Any, Any]])


def register(os_name: str) -> Callable[[C], C]:
    def decorator(cls: C) -> C:
        _REGISTRY.setdefault(cls.component, {})[os_name] = cls
        return cls

    return decorator


def _load_platform_collectors(os_name: str) -> None:
    if os_name == "Linux":
        import hwbench.collectors.linux  # noqa: F401


def get_collector(component: str, os_name: str | None = None) -> Collector[Any, Any]:
    os_name = os_name or platform.system()
    _load_platform_collectors(os_name)
    try:
        cls = _REGISTRY[component][os_name]
    except KeyError as exc:
        raise UnsupportedPlatformError(
            f"Aucun collecteur « {component} » pour la plateforme {os_name}"
        ) from exc
    return cls()
