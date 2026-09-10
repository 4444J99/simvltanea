"""SIMVLTANEA Core Engine & Runtime Package.

Provides the composition compiler, authoring model, layout definitions,
headless browser runtime, and multi-stream rendering engine.
"""

from .composition import (
    ENGINE_VERSION,
    SCHEMA_VERSION,
    ORIENTATIONS,
    StateError,
    load_state,
    save_state,
    validate_state,
    resolve_at,
    pixel_placements,
    from_authoring_model,
)
from .composition_model import (
    CompositionModel,
    Loop,
    Layout,
    Placement,
    Event,
    HoldEvent,
    ReleaseEvent,
    SwapEvent,
    RerollEvent,
    MoveEvent,
)
from .artifact001_layouts import build_artifact001, AUTHORED

__all__ = [
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "ORIENTATIONS",
    "StateError",
    "load_state",
    "save_state",
    "validate_state",
    "resolve_at",
    "pixel_placements",
    "from_authoring_model",
    "CompositionModel",
    "Loop",
    "Layout",
    "Placement",
    "Event",
    "HoldEvent",
    "ReleaseEvent",
    "SwapEvent",
    "RerollEvent",
    "MoveEvent",
    "build_artifact001",
    "AUTHORED",
]
