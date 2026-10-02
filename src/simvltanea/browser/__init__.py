"""Public API for the browser feature; implementations load on demand."""
from importlib import import_module

_EXPORTS = {'browser_runtime': 'browser_runtime',
 'HERE': 'browser_runtime',
 'compile_plan': 'browser_runtime',
 'build_preview': 'browser_runtime'}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"{__name__} has no public attribute {name!r}")
    module = import_module(f"{__name__}.{_EXPORTS[name]}")
    value = module if name == _EXPORTS[name] else getattr(module, name)
    globals()[name] = value
    return value
