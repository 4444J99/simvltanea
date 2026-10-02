"""Public API for the rendering feature; implementations load on demand."""
from importlib import import_module

_EXPORTS = {'render_triptych': 'render_triptych',
 'Panel': 'render_triptych',
 'Placement': 'render_triptych',
 'Segment': 'render_triptych',
 'Settings': 'render_triptych',
 'probe_audio_channels': 'render_triptych'}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"{__name__} has no public attribute {name!r}")
    module = import_module(f"{__name__}.{_EXPORTS[name]}")
    value = module if name == _EXPORTS[name] else getattr(module, name)
    globals()[name] = value
    return value
