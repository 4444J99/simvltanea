"""Public API for the authoring feature; implementations load on demand."""
from importlib import import_module

_EXPORTS = {'composition': 'composition',
 'composition_model': 'composition_model',
 'artifact001_layouts': 'artifact001_layouts',
 'ENGINE_VERSION': 'composition',
 'SCHEMA_VERSION': 'composition',
 'ORIENTATIONS': 'composition',
 'RNG': 'composition',
 'StateError': 'composition',
 'load_state': 'composition',
 'save_state': 'composition',
 'validate_state': 'composition',
 'validate_audio': 'composition',
 'resolve_at': 'composition',
 'pixel_placements': 'composition',
 'from_authoring_model': 'composition',
 'sha256_file': 'composition',
 'render_from_args': 'composition',
 'Composition': 'composition_model',
 'LoopState': 'composition_model',
 'Layout': 'composition_model',
 'Placement': 'composition_model',
 'SilentAudio': 'composition_model',
 'SoundtrackAudio': 'composition_model',
 'SpatialLoopsAudio': 'composition_model',
 'build_artifact001': 'artifact001_layouts',
 'AUTHORED': 'artifact001_layouts'}
__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"{__name__} has no public attribute {name!r}")
    module = import_module(f"{__name__}.{_EXPORTS[name]}")
    value = module if name == _EXPORTS[name] else getattr(module, name)
    globals()[name] = value
    return value
