"""Functional public API for independently clocked audiovisual compositions.

The established implementation stays in ``simvltanea`` for import, asset, and
provenance compatibility. Both namespaces use the same classes and functions.
"""
from .authoring import (
    Composition, LoopState, Layout, Placement, SilentAudio, SoundtrackAudio,
    SpatialLoopsAudio, StateError, from_authoring_model, load_state, save_state,
    validate_state, resolve_at, pixel_placements,
)

__all__ = [
    "Composition", "LoopState", "Layout", "Placement", "SilentAudio",
    "SoundtrackAudio", "SpatialLoopsAudio", "StateError", "from_authoring_model",
    "load_state", "save_state", "validate_state", "resolve_at", "pixel_placements",
]
