"""Public API for the generators feature; implementations load on demand."""
from importlib import import_module

_EXPORTS = {'make_artifact_001': 'make_artifact_001',
 'make_audio_fixture': 'make_audio_fixture',
 'make_runtime_fixture': 'make_runtime_fixture'}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"{__name__} has no public attribute {name!r}")
    module = import_module(f"{__name__}.{_EXPORTS[name]}")
    value = module if name == _EXPORTS[name] else getattr(module, name)
    globals()[name] = value
    return value
