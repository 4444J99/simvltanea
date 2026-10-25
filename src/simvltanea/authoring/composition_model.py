#!/usr/bin/env python3
"""Declarative composition state for independent video loops and paired layouts.

This module is deliberately renderer-agnostic.  It separates temporal/content
state from presentation geometry so orientation changes cannot mutate loop state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import colorsys
import hashlib
import json
import math
import random
from typing import Any, Sequence

SCHEMA_VERSION = "visual-form-composition/v1"
AUDIO_SCHEMA_VERSION = "visual-form-composition/v1.1"
ENGINE_VERSION = "0.1.0"
ORIENTATIONS = ("portrait", "landscape")
FIT_MODES = {"cover", "contain"}
AudioControl = int | float | str


@dataclass(frozen=True)
class SilentAudio:
    mode: str = "none"
    routing: None = None
    generative: None = None


@dataclass(frozen=True)
class SoundtrackAudio:
    source: str
    sha256: str
    duration: str | int
    volume: AudioControl = 1.0
    loop: bool = True
    fade_in_seconds: AudioControl = 0.0
    fade_out_seconds: AudioControl = 0.0
    mode: str = "soundtrack"


@dataclass(frozen=True)
class LoopAudio:
    gain: AudioControl = 1.0
    mute_on_hold: bool = True


@dataclass(frozen=True)
class SpatialLoopsAudio:
    master_volume: AudioControl = 1.0
    spatial_panning: bool = True
    per_loop: dict[str, LoopAudio] = field(default_factory=dict)
    mode: str = "spatial_loops"


Audio = SilentAudio | SoundtrackAudio | SpatialLoopsAudio


def audio_to_dict(value: Audio | None) -> dict[str, Any]:
    if value is None:
        return asdict(SilentAudio())
    if not isinstance(value, (SilentAudio, SoundtrackAudio, SpatialLoopsAudio)):
        raise ValueError("audio must be a typed audio specification")
    expected = {SilentAudio: "none", SoundtrackAudio: "soundtrack", SpatialLoopsAudio: "spatial_loops"}
    if value.mode != expected[type(value)]:
        raise ValueError("audio type and mode disagree")
    if isinstance(value, SpatialLoopsAudio) and (not isinstance(value.per_loop, dict) or
                                               not all(isinstance(v, LoopAudio) for v in value.per_loop.values())):
        raise ValueError("spatial per_loop entries must be typed LoopAudio controls")
    return asdict(value)


def audio_from_dict(value: Any) -> Audio | None:
    if value is None:
        return None
    from simvltanea.authoring.composition import validate_audio
    validate_audio(value)
    mode = value["mode"]
    if mode == "none":
        return SilentAudio(**value)
    if mode == "soundtrack":
        return SoundtrackAudio(**value)
    return SpatialLoopsAudio(**dict(value, per_loop={key: LoopAudio(**control)
                                                    for key, control in value.get("per_loop", {}).items()}))


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
    color_profile: Any = None
    subject_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.color_profile, list):
            object.__setattr__(self, "color_profile", tuple(self.color_profile))
        if isinstance(self.subject_tags, list):
            object.__setattr__(self, "subject_tags", tuple(self.subject_tags))

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
    audio: Audio | None = None

    @property
    def loop_ids(self) -> tuple[str, ...]:
        return tuple(loop.id for loop in self.loops)

    def validate(self) -> None:
        if self.schema_version not in (SCHEMA_VERSION, AUDIO_SCHEMA_VERSION):
            raise ValueError(f"unsupported schema version: {self.schema_version}")
        if self.engine_version != ENGINE_VERSION:
            raise ValueError(f"unsupported engine version: {self.engine_version}")
        if not self.loops:
            raise ValueError("composition must contain an independent loop")
        for loop in self.loops:
            loop.validate()
        if len(self.loop_ids) != len(set(self.loop_ids)):
            raise ValueError("loop ids must be unique")
        from simvltanea.authoring.composition import validate_audio
        validate_audio(audio_to_dict(self.audio), set(self.loop_ids),
                       1 if self.schema_version == SCHEMA_VERSION else "1.1")
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
        result = {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "id": self.id,
            "seed": self.seed,
            "loops": [{key: value for key, value in loop.__dict__.items()
                       if not ((key == "color_profile" and value is None)
                               or (key == "subject_tags" and not value))}
                      for loop in self.loops],
            "layouts": [{"id": l.id, "orientation": l.orientation, "placements": [p.__dict__ for p in l.placements]} for l in self.layouts],
            "event_history": list(self.event_history),
        }
        # Keep historical v1 serialized snapshots byte-compatible in structure.
        if self.schema_version == AUDIO_SCHEMA_VERSION:
            result["audio"] = audio_to_dict(self.audio)
        return result

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
            audio=audio_from_dict(raw.get("audio")),
        )
        comp.validate()
        return comp


@dataclass(frozen=True)
class SliceRect:
    """Normalized viewport crop rectangle within a media frame surface.

    Coordinates lie strictly within [0.0, 1.0]. Full frame (0, 0, 1, 1) is
    expressly forbidden in amalgamated mode per the ACE source ledger directive.
    """
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in ("x", "y", "width", "height"):
            val = getattr(self, name)
            if type(val) not in (int, float) or not math.isfinite(val):
                raise ValueError(f"SliceRect {name} must be finite, got {val}")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError(f"SliceRect dimensions must be positive, got width={self.width}, height={self.height}")
        if self.x < -1e-9 or self.y < -1e-9 or self.width > 1.000001 or self.height > 1.000001:
            raise ValueError(f"SliceRect coordinates must lie within [0.0, 1.0], got ({self.x}, {self.y}, {self.width}, {self.height})")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError(f"SliceRect exceeds normalized canvas bounds: x+width={self.x + self.width}, y+height={self.y + self.height}")

    @property
    def is_full_frame(self) -> bool:
        return (math.isclose(self.x, 0.0, abs_tol=1e-5) and
                math.isclose(self.y, 0.0, abs_tol=1e-5) and
                math.isclose(self.width, 1.0, abs_tol=1e-5) and
                math.isclose(self.height, 1.0, abs_tol=1e-5))

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.width, self.height]

    def to_rational_strings(self) -> list[str]:
        from fractions import Fraction
        return [
            str(Fraction(self.x).limit_denominator(10000)),
            str(Fraction(self.y).limit_denominator(10000)),
            str(Fraction(self.width).limit_denominator(10000)),
            str(Fraction(self.height).limit_denominator(10000)),
        ]

    def __iter__(self):
        yield self.x
        yield self.y
        yield self.width
        yield self.height

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, int):
            return (self.x, self.y, self.width, self.height)[item]
        if item in ("x", "y", "width", "height"):
            return getattr(self, item)
        raise KeyError(f"invalid SliceRect index/key: {item}")


@dataclass(frozen=True)
class AmalgamatedPanel:
    """Pairing of a selected clip with its amalgamated SliceRect viewport."""
    clip: Any
    viewport: SliceRect

    def __iter__(self):
        yield self.clip
        yield self.viewport

    def __getitem__(self, item: Any) -> Any:
        if item in (0, "clip"):
            return self.clip
        if item in (1, "viewport", "slice_rect"):
            return self.viewport
        raise KeyError(f"invalid AmalgamatedPanel key/index: {item}")

    @property
    def slice_rect(self) -> SliceRect:
        return self.viewport

    def to_dict(self) -> dict[str, Any]:
        clip_repr = self.clip if isinstance(self.clip, (dict, str, int, float)) else getattr(self.clip, "__dict__", str(self.clip))
        return {
            "clip": clip_repr,
            "viewport": self.viewport.to_dict(),
            "slice_rect": self.viewport.to_dict(),
        }


def _normalize_color_profile(profile: Any, fallback_seed: str = "") -> tuple[float, float, float]:
    """Normalize color profile representation into RGB floats in [0.0, 1.0]."""
    if profile is None:
        h = hashlib.sha256(str(fallback_seed).encode("utf-8")).digest()
        return (h[0] / 255.0, h[1] / 255.0, h[2] / 255.0)

    if isinstance(profile, str):
        s = profile.strip().lstrip("#")
        if len(s) == 6:
            try:
                r = int(s[0:2], 16) / 255.0
                g = int(s[2:4], 16) / 255.0
                b = int(s[4:6], 16) / 255.0
                return (r, g, b)
            except ValueError:
                pass
        elif len(s) == 3:
            try:
                r = int(s[0] * 2, 16) / 255.0
                g = int(s[1] * 2, 16) / 255.0
                b = int(s[2] * 2, 16) / 255.0
                return (r, g, b)
            except ValueError:
                pass

    if isinstance(profile, (list, tuple)) and len(profile) >= 3:
        try:
            vals = [float(v) for v in profile[:3]]
            if any(v > 1.0 for v in vals):
                vals = [v / 255.0 for v in vals]
            return (max(0.0, min(1.0, vals[0])), max(0.0, min(1.0, vals[1])), max(0.0, min(1.0, vals[2])))
        except (ValueError, TypeError):
            pass

    if isinstance(profile, dict):
        if "r" in profile and "g" in profile and "b" in profile:
            try:
                vals = [float(profile["r"]), float(profile["g"]), float(profile["b"])]
                if any(v > 1.0 for v in vals):
                    vals = [v / 255.0 for v in vals]
                return (max(0.0, min(1.0, vals[0])), max(0.0, min(1.0, vals[1])), max(0.0, min(1.0, vals[2])))
            except (ValueError, TypeError):
                pass
        if "hue" in profile:
            try:
                h = float(profile["hue"])
                if h > 1.0:
                    h = (h % 360.0) / 360.0
                s = float(profile.get("saturation", profile.get("s", 1.0)))
                if s > 1.0:
                    s /= 100.0
                l = float(profile.get("luminance", profile.get("lightness", profile.get("l", 0.5))))
                if l > 1.0:
                    l /= 100.0
                rgb = colorsys.hls_to_rgb(h, l, s)
                return (max(0.0, min(1.0, rgb[0])), max(0.0, min(1.0, rgb[1])), max(0.0, min(1.0, rgb[2])))
            except (ValueError, TypeError):
                pass

    h = hashlib.sha256(str(fallback_seed).encode("utf-8")).digest()
    return (h[0] / 255.0, h[1] / 255.0, h[2] / 255.0)


def _normalize_subject_tags(tags: Any, fallback_seed: str = "") -> set[str]:
    """Normalize subject tags into a set of lowercase strings with fallback."""
    if tags is None or (isinstance(tags, (list, tuple, set)) and len(tags) == 0):
        h = hashlib.sha256(str(fallback_seed).encode("utf-8")).digest()
        return {f"tag_{h[3] % 8}", f"subject_{h[4] % 8}"}
    if isinstance(tags, str):
        return {t.strip().lower() for t in tags.split(",") if t.strip()}
    if isinstance(tags, (list, tuple, set)):
        cleaned = {str(t).strip().lower() for t in tags if str(t).strip()}
        if cleaned:
            return cleaned
        h = hashlib.sha256(str(fallback_seed).encode("utf-8")).digest()
        return {f"tag_{h[3] % 8}", f"subject_{h[4] % 8}"}
    return set()


def _extract_clip_features(clip: Any) -> tuple[str, Any, Any]:
    """Extract (clip_id, color_profile, subject_tags) from a candidate record."""
    if isinstance(clip, dict):
        raw_id = clip.get("id") or clip.get("source") or clip.get("path")
        if not raw_id:
            raise ValueError("clip requires a stable id, source, or path")
        cid = str(raw_id)
        cp = clip.get("color_profile") or clip.get("color")
        tags = clip.get("subject_tags") or clip.get("tags") or clip.get("subjects")
        return cid, cp, tags
    if isinstance(clip, str):
        return clip, None, None
    raw_id = getattr(clip, "id", None) or getattr(clip, "source", None) or getattr(clip, "path", None)
    if not raw_id:
        raise ValueError("clip requires a stable id, source, or path")
    cid = str(raw_id)
    cp = getattr(clip, "color_profile", None)
    tags = getattr(clip, "subject_tags", None)
    return cid, cp, tags


def amalgamate_viewports(panel_count: int, seed: int | str = 0, mode: str = "ribbon") -> list[SliceRect]:
    """Generate panel_count SliceRect viewports that amalgamate into one evolving image.

    Supports 3 <= panel_count <= 10. Guarantees no panel displays the full clip surface,
    every coordinate lies strictly within [0.0, 1.0], and panels partition/overlap-stitch
    across the normalized canvas.
    """
    if not isinstance(panel_count, int) or not (3 <= panel_count <= 10):
        raise ValueError(f"panel_count must be an integer between 3 and 10, got {panel_count}")

    rng = random.Random(str(seed))

    if mode in ("ribbon", "horizontal", "horizontal_ribbon"):
        overlap = 0.15 + (rng.random() * 0.05)
        w = min(0.85, (1.0 + overlap * (panel_count - 1)) / panel_count)
        w = round(w, 6)
        dx = (1.0 - w) / (panel_count - 1)
        h = round(0.92 + (rng.random() * 0.06), 6)

        rects = []
        for i in range(panel_count):
            if i == 0:
                x = 0.0
            elif i == panel_count - 1:
                x = round(1.0 - w, 6)
            else:
                x = round(i * dx, 6)

            max_y = max(0.0, 1.0 - h)
            y = round(rng.random() * max_y, 6)
            x = max(0.0, min(1.0 - w, x))
            y = max(0.0, min(1.0 - h, y))

            rect = SliceRect(x=x, y=y, width=w, height=h)
            if rect.is_full_frame:
                raise ValueError("amalgamated viewport must not display full clip frame")
            rects.append(rect)
        return rects

    elif mode in ("vertical", "vertical_ribbon"):
        overlap = 0.15 + (rng.random() * 0.05)
        h = min(0.85, (1.0 + overlap * (panel_count - 1)) / panel_count)
        h = round(h, 6)
        dy = (1.0 - h) / (panel_count - 1)
        w = round(0.92 + (rng.random() * 0.06), 6)

        rects = []
        for i in range(panel_count):
            if i == 0:
                y = 0.0
            elif i == panel_count - 1:
                y = round(1.0 - h, 6)
            else:
                y = round(i * dy, 6)

            max_x = max(0.0, 1.0 - w)
            x = round(rng.random() * max_x, 6)
            x = max(0.0, min(1.0 - w, x))
            y = max(0.0, min(1.0 - h, y))

            rect = SliceRect(x=x, y=y, width=w, height=h)
            if rect.is_full_frame:
                raise ValueError("amalgamated viewport must not display full clip frame")
            rects.append(rect)
        return rects

    elif mode in ("grid", "mosaic"):
        cols = 3 if panel_count <= 6 else 4
        rows = math.ceil(panel_count / cols)
        cell_w = round(min(0.85, 1.0 / cols + 0.05), 6)
        cell_h = round(min(0.85, 1.0 / rows + 0.05), 6)
        rects = []
        for i in range(panel_count):
            r = i // cols
            c = i % cols
            x = round(min(1.0 - cell_w, c * ((1.0 - cell_w) / max(1, cols - 1))), 6)
            y = round(min(1.0 - cell_h, r * ((1.0 - cell_h) / max(1, rows - 1))), 6)
            rect = SliceRect(x=x, y=y, width=cell_w, height=cell_h)
            if rect.is_full_frame:
                raise ValueError("amalgamated viewport must not display full clip frame")
            rects.append(rect)
        return rects

    else:
        raise ValueError(f"unsupported amalgamation mode: {mode}")


def color_subject_affinity(clip_a: Any, clip_b: Any) -> float:
    """Calculate normalized color proximity + subject tag affinity in [0.0, 1.0]."""
    id_a, cp_a, tags_a = _extract_clip_features(clip_a)
    id_b, cp_b, tags_b = _extract_clip_features(clip_b)

    has_explicit_color = (cp_a is not None) or (cp_b is not None)
    has_explicit_tags = (tags_a is not None and bool(tags_a)) or (tags_b is not None and bool(tags_b))

    rgb_a = _normalize_color_profile(cp_a, fallback_seed=id_a)
    rgb_b = _normalize_color_profile(cp_b, fallback_seed=id_b)

    dr = rgb_a[0] - rgb_b[0]
    dg = rgb_a[1] - rgb_b[1]
    db = rgb_a[2] - rgb_b[2]
    dist = math.sqrt(dr * dr + dg * dg + db * db)
    max_dist = math.sqrt(3.0)
    color_sim = max(0.0, min(1.0, 1.0 - (dist / max_dist)))

    set_a = _normalize_subject_tags(tags_a, fallback_seed=id_a)
    set_b = _normalize_subject_tags(tags_b, fallback_seed=id_b)
    union = set_a | set_b
    if not union:
        subject_sim = 1.0 if not has_explicit_tags else 0.5
    else:
        subject_sim = len(set_a & set_b) / len(union)

    if has_explicit_color and not has_explicit_tags:
        score = color_sim
    elif has_explicit_tags and not has_explicit_color:
        score = subject_sim
    else:
        score = 0.5 * color_sim + 0.5 * subject_sim

    return round(max(0.0, min(1.0, score)), 6)


def select_neighbor_sequence(candidates: Sequence[Any], panel_count: int, seed: int | str = 0) -> list[AmalgamatedPanel]:
    """Select a sequence of neighbor clips maximizing color/subject affinity paired with amalgamated SliceRects."""
    if not isinstance(panel_count, int) or not (3 <= panel_count <= 10):
        raise ValueError(f"panel_count must be an integer between 3 and 10, got {panel_count}")
    cand_list = list(candidates)
    if len(cand_list) < panel_count:
        raise ValueError(f"insufficient candidates: requested {panel_count} panels but only have {len(cand_list)} candidates")

    rng = random.Random(str(seed))
    first_idx = rng.randrange(len(cand_list))
    selected = [cand_list[first_idx]]
    remaining = [c for i, c in enumerate(cand_list) if i != first_idx]

    while len(selected) < panel_count:
        prev = selected[-1]
        best_cand = None
        best_affinity = -1.0
        best_key = ""
        for cand in remaining:
            aff = color_subject_affinity(prev, cand)
            cid = _extract_clip_features(cand)[0]
            if aff > best_affinity or (math.isclose(aff, best_affinity, abs_tol=1e-7) and (best_cand is None or cid < best_key)):
                best_affinity = aff
                best_cand = cand
                best_key = cid
        selected.append(best_cand)
        remaining.remove(best_cand)

    viewports = amalgamate_viewports(panel_count=panel_count, seed=seed)
    return [AmalgamatedPanel(clip=clip, viewport=vp) for clip, vp in zip(selected, viewports)]
