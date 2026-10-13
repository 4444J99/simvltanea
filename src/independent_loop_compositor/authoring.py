"""Source-neutral authoring API backed by the existing composition implementation."""
from simvltanea.authoring import (
    ENGINE_VERSION, SCHEMA_VERSION, ORIENTATIONS, Composition, LoopState, Layout,
    Placement, SilentAudio, SoundtrackAudio, SpatialLoopsAudio, StateError,
    from_authoring_model, load_state, save_state, validate_state, validate_audio,
    resolve_at, pixel_placements,
)

__all__ = [
    "ENGINE_VERSION", "SCHEMA_VERSION", "ORIENTATIONS", "Composition", "LoopState",
    "Layout", "Placement", "SilentAudio", "SoundtrackAudio", "SpatialLoopsAudio",
    "StateError", "from_authoring_model", "load_state", "save_state",
    "validate_state", "validate_audio", "resolve_at", "pixel_placements",
]
