#!/usr/bin/env python3
"""Declarative composition state for independent video loops and paired layouts.

This module is deliberately renderer-agnostic.  It separates temporal/content
state from presentation geometry so orientation changes cannot mutate loop state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import random
from typing import Any

SCHEMA_VERSION = "visual-form-composition/v1"
ENGINE_VERSION = "0.1.0"
ORIENTATIONS = ("portrait", "landscape")
FIT_MODES = {"cover", "contain"}


@dataclass(frozen=True)
class LoopState:
    id: str
    source: str
    trim_in: float = 0.0
    trim_out: float | None = None
    rate: float = 1.0
    offset: float = 0.0
    held_at: float | None = None
    selection_seed: int = 0
    reroll_index: int = 0
    audible: bool = False

    def validate(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("loop identity must be nonempty")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError(f"loop {self.id}: source must be nonempty")
        for name in ("trim_in", "trim_out", "rate", "offset", "held_at"):
            value = getattr(self, name)
            if value is None and name in ("trim_out", "held_at"):
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"loop {self.id}: {name} must be finite")
        if self.rate <= 0 or self.trim_in < 0:
            raise ValueError(f"loop {self.id}: rate must be positive and trim_in nonnegative")
        if self.trim_out is not None and self.trim_out <= self.trim_in:
            raise ValueError(f"loop {self.id}: trim_out must exceed trim_in")
        if type(self.reroll_index) is not int or self.reroll_index < 0:
            raise ValueError(f"loop {self.id}: reroll_index must be a nonnegative integer")
        if type(self.selection_seed) is not int or type(self.audible) is not bool:
            raise ValueError(f"loop {self.id}: invalid selection/audio state")

    def media_time(self, clock: float) -> float:
        if self.rate <= 0:
            raise ValueError(f"loop {self.id}: rate must be positive")
        elapsed = self.held_at if self.held_at is not None else clock
        value = self.trim_in + self.offset + elapsed * self.rate
        if self.trim_out is None:
            return value
        span = self.trim_out - self.trim_in
        if span <= 0:
            raise ValueError(f"loop {self.id}: trim_out must exceed trim_in")
        return self.trim_in + ((value - self.trim_in) % span)


@dataclass(frozen=True)
class Placement:
    loop_id: str
    x: float
    y: float
    width: float
    height: float
    z: int = 0
    fit: str = "cover"
    focal_x: float = 0.5
    focal_y: float = 0.5

    def validate(self) -> None:
        if type(self.z) is not int:
            raise ValueError(f"{self.loop_id}: z-order must be an integer")
        if self.fit not in FIT_MODES:
            raise ValueError(f"{self.loop_id}: unsupported fit {self.fit}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"{self.loop_id}: placement dimensions must be positive")
        for name, value in (("x", self.x), ("y", self.y), ("width", self.width), ("height", self.height), ("focal_x", self.focal_x), ("focal_y", self.focal_y)):
            if not 0 <= value <= 1:
                raise ValueError(f"{self.loop_id}: {name} must be normalized to 0..1")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError(f"{self.loop_id}: placement exceeds normalized canvas")


@dataclass(frozen=True)
class Layout:
    id: str
    orientation: str
    placements: tuple[Placement, ...]

    def validate(self, loop_ids: tuple[str, ...]) -> None:
        if self.orientation not in ORIENTATIONS:
            raise ValueError(f"{self.id}: invalid orientation")
        ids = tuple(p.loop_id for p in self.placements)
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id}: a loop is mapped more than once")
        if set(ids) != set(loop_ids):
            missing = sorted(set(loop_ids) - set(ids))
            extra = sorted(set(ids) - set(loop_ids))
            raise ValueError(f"{self.id}: one-to-one mapping failed; missing={missing}, extra={extra}")
        for placement in self.placements:
            placement.validate()


@dataclass(frozen=True)
class Composition:
    id: str
    loops: tuple[LoopState, ...]
    layouts: tuple[Layout, ...]
    seed: int = 0
    event_history: tuple[dict[str, Any], ...] = ()
    schema_version: str = SCHEMA_VERSION
    engine_version: str = ENGINE_VERSION

    @property
    def loop_ids(self) -> tuple[str, ...]:
        return tuple(loop.id for loop in self.loops)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version: {self.schema_version}")
        if self.engine_version != ENGINE_VERSION:
            raise ValueError(f"unsupported engine version: {self.engine_version}")
        if not self.loops:
            raise ValueError("composition must contain an independent loop")
        for loop in self.loops:
            loop.validate()
        if len(self.loop_ids) != len(set(self.loop_ids)):
            raise ValueError("loop ids must be unique")
        orientations = {layout.orientation for layout in self.layouts}
        if orientations != set(ORIENTATIONS) or len(self.layouts) != len(ORIENTATIONS):
            raise ValueError("composition requires authored portrait and landscape layouts")
        for layout in self.layouts:
            layout.validate(self.loop_ids)

    def layout(self, orientation: str) -> Layout:
        matches = [layout for layout in self.layouts if layout.orientation == orientation]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one {orientation} layout")
        return matches[0]

    def apply(self, event: dict[str, Any], clock: float) -> "Composition":
        """Apply deterministic model-level controls without touching unrelated clocks.

        hold: freezes one loop at its current local elapsed time; release resumes from
        that local time by rebasing offset. reroll advances only the selected loop's
        deterministic selection counter. swap exchanges sources and source-selection
        state while retaining loop IDs/clocks. move changes presentation placement only.
        """
        kind = event["type"]
        loops = list(self.loops)
        layouts = list(self.layouts)
        by_id = {loop.id: i for i, loop in enumerate(loops)}
        if kind in {"hold", "release", "reroll"}:
            loop_id = event["loop_id"]
            i = by_id[loop_id]
            loop = loops[i]
            if kind == "hold":
                loops[i] = replace(loop, held_at=clock if loop.held_at is None else loop.held_at)
            elif kind == "release":
                if loop.held_at is not None:
                    loops[i] = replace(loop, offset=loop.offset + (loop.held_at - clock) * loop.rate, held_at=None)
            else:
                loops[i] = replace(loop, reroll_index=loop.reroll_index + 1)
        elif kind == "swap":
            a, b = event["a"], event["b"]
            ia, ib = by_id[a], by_id[b]
            la, lb = loops[ia], loops[ib]
            fields_a = dict(source=lb.source, selection_seed=lb.selection_seed, reroll_index=lb.reroll_index)
            fields_b = dict(source=la.source, selection_seed=la.selection_seed, reroll_index=la.reroll_index)
            loops[ia], loops[ib] = replace(la, **fields_a), replace(lb, **fields_b)
        elif kind == "move":
            orientation, loop_id = event["orientation"], event["loop_id"]
            for li, layout in enumerate(layouts):
                if layout.orientation != orientation:
                    continue
                placements = list(layout.placements)
                pi = next(i for i, p in enumerate(placements) if p.loop_id == loop_id)
                placements[pi] = replace(placements[pi], **event["geometry"])
                layouts[li] = replace(layout, placements=tuple(placements))
        else:
            raise ValueError(f"unsupported event type: {kind}")
        updated = replace(self, loops=tuple(loops), layouts=tuple(layouts), event_history=self.event_history + (dict(event, clock=clock),))
        updated.validate()
        return updated

    def choose_source(self, loop_id: str, ordered_bank: tuple[str, ...]) -> str:
        if not ordered_bank:
            raise ValueError("media bank cannot be empty")
        loop = next(loop for loop in self.loops if loop.id == loop_id)
        rng = random.Random(f"{self.seed}:{loop.selection_seed}:{loop.reroll_index}:{loop.id}")
        return ordered_bank[rng.randrange(len(ordered_bank))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "id": self.id,
            "seed": self.seed,
            "loops": [loop.__dict__ for loop in self.loops],
            "layouts": [{"id": l.id, "orientation": l.orientation, "placements": [p.__dict__ for p in l.placements]} for l in self.layouts],
            "event_history": list(self.event_history),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Composition":
        comp = cls(
            id=raw["id"], seed=int(raw.get("seed", 0)),
            loops=tuple(LoopState(**item) for item in raw["loops"]),
            layouts=tuple(Layout(id=item["id"], orientation=item["orientation"], placements=tuple(Placement(**p) for p in item["placements"])) for item in raw["layouts"]),
            event_history=tuple(raw.get("event_history", ())),
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            engine_version=raw.get("engine_version", ENGINE_VERSION),
        )
        comp.validate()
        return comp
