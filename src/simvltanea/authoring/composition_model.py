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
            return tuple(max(0.0, min(1.0, v)) for v in vals)
        except (TypeError, ValueError):
            pass

    return _normalize_color_profile(None, fallback_seed)


def export_amalgamated_manifest(
    panel_count: int,
    media_candidates: Sequence[Any],
    seed: int = 0,
    preview_limit: int | None = None,
) -> dict[str, Any]:
    """Export a canonical amalgamated composition manifest with SHA-256 digest."""
    if not isinstance(panel_count, int) or panel_count < 1:
        raise ValueError("panel_count must be a positive integer")
    if not media_candidates:
        raise ValueError("media_candidates cannot be empty")

    from simvltanea.authoring.composition import MAX_AMALGAMATED_DECODERS
    if panel_count > MAX_AMALGAMATED_DECODERS:
        raise ValueError(f"panel_count {panel_count} exceeds MAX_AMALGAMATED_DECODERS {MAX_AMALGAMATED_DECODERS}")

    rng = random.Random(seed)
    selected = []
    for i in range(panel_count):
        clip = rng.choice(media_candidates)
        # Deterministic non-full-frame viewport
        x = rng.uniform(0.05, 0.4)
        y = rng.uniform(0.05, 0.4)
        w = rng.uniform(0.3, 0.5)
        h = rng.uniform(0.3, 0.5)
        if x + w > 0.95:
            w = 0.95 - x
        if y + h > 0.95:
            h = 0.95 - y
        viewport = SliceRect(x=x, y=y, width=w, height=h)
        selected.append(AmalgamatedPanel(clip=clip, viewport=viewport))

    manifest = {
        "schema": "simvltanea.amalgamated_manifest.v1",
        "panel_count": panel_count,
        "active_decoders": panel_count,
        "preview_mode": "amalgamated" if preview_limit is None else "bounded",
        "preview_limit": preview_limit,
        "panels": [p.to_dict() for p in selected],
    }
    payload = {k: v for k, v in manifest.items() if k != "digest"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    manifest["digest"] = digest
    return manifest


def verify_amalgamated_manifest(manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    """Verify an amalgamated manifest against structural and digest constraints."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return False, ["Manifest must be a dictionary"]

    # 1. Schema
    if manifest.get("schema") != "simvltanea.amalgamated_manifest.v1":
        errors.append("Unsupported or missing schema")

    # 2. Panel count
    panel_count = manifest.get("panel_count")
    if not isinstance(panel_count, int) or panel_count < 1:
        errors.append("panel_count must be a positive integer")

    # 3. Active decoders
    active = manifest.get("active_decoders")
    if not isinstance(active, int) or active < 1 or (isinstance(panel_count, int) and active > panel_count):
        errors.append("active_decoders must be a positive integer <= panel_count")

    from simvltanea.authoring.composition import MAX_AMALGAMATED_DECODERS
    if isinstance(active, int) and active > MAX_AMALGAMATED_DECODERS:
        errors.append(f"active_decoders {active} exceeds MAX_AMALGAMATED_DECODERS {MAX_AMALGAMATED_DECODERS}")

    # 4. Preview mode
    mode = manifest.get("preview_mode")
    if mode not in ("amalgamated", "bounded"):
        errors.append("preview_mode must be amalgamated or bounded")

    # 5. Panels and viewports
    panels = manifest.get("panels")
    if not isinstance(panels, list) or (isinstance(panel_count, int) and len(panels) != panel_count):
        errors.append("panels must be a list of length panel_count")
    else:
        for idx, panel in enumerate(panels):
            if not isinstance(panel, dict):
                errors.append(f"Panel {idx} is not a dictionary")
                continue
            vp = panel.get("viewport") or panel.get("slice_rect")
            if not isinstance(vp, dict):
                errors.append(f"Panel {idx} missing valid viewport/slice_rect dict")
                continue
            try:
                rect = SliceRect(
                    x=float(vp["x"]),
                    y=float(vp["y"]),
                    width=float(vp["width"]),
                    height=float(vp["height"]),
                )
                if rect.is_full_frame:
                    errors.append(f"Panel {idx} viewport is full frame (forbidden in amalgamated mode)")
            except Exception as e:
                errors.append(f"Panel {idx} has invalid SliceRect: {e}")

    # 6. Digest verification
    raw_digest = manifest.get("digest")
    if not raw_digest:
        errors.append("Manifest missing 'digest'")
    else:
        if isinstance(raw_digest, dict):
            expected_hex = raw_digest.get("value") or raw_digest.get("hex") or ""
        elif isinstance(raw_digest, str):
            expected_hex = raw_digest.split(":")[-1] if raw_digest.startswith("sha256:") else raw_digest
        else:
            expected_hex = ""

        payload_to_verify = {k: v for k, v in manifest.items() if k != "digest"}
        canonical_bytes = json.dumps(payload_to_verify, sort_keys=True).encode("utf-8")
        computed_hex = hashlib.sha256(canonical_bytes).hexdigest()

        if expected_hex != computed_hex:
            errors.append(f"SHA-256 digest mismatch: expected {expected_hex}, computed {computed_hex}")

    return (len(errors) == 0, errors)


RELEASE_SEAL_SCHEMA = "simvltanea.release_seal.v1"


def build_simvltanea_release_seal(
    amalgamated_manifest: dict[str, Any],
    custody_parity_report: dict[str, Any],
) -> dict[str, Any]:
    """Build a canonical SHA-256 digested release seal for SIMVLTANEA spatial composition and custody."""
    checks: dict[str, Any] = {}

    # 1. Spatial Amalgamation Manifest validation
    manifest_ok, manifest_errors = verify_amalgamated_manifest(amalgamated_manifest)
    checks["amalgamated_manifest"] = {
        "passed": manifest_ok,
        "errors": manifest_errors,
        "panel_count": amalgamated_manifest.get("panel_count") if isinstance(amalgamated_manifest, dict) else None,
        "active_decoders": amalgamated_manifest.get("active_decoders") if isinstance(amalgamated_manifest, dict) else None,
    }

    # 2. Custody Parity validation
    custody_errors: list[str] = []
    canonical_parity_ok = False
    receipt_verified = False

    if not isinstance(custody_parity_report, dict):
        custody_errors.append("Custody parity report must be a dictionary")
    else:
        # Check canonical parity
        if "canonical_parity_ok" in custody_parity_report:
            canonical_parity_ok = bool(custody_parity_report["canonical_parity_ok"])
        elif "canonical_assigned" in custody_parity_report:
            canonical_parity_ok = bool(custody_parity_report["canonical_assigned"].get("clean_parity", False))
        elif custody_parity_report.get("status") == "PASS":
            canonical_parity_ok = True

        if not canonical_parity_ok:
            custody_errors.append("Canonical repository lacks clean parity")

        # Check custody receipt
        if "receipt_verified" in custody_parity_report:
            receipt_verified = bool(custody_parity_report["receipt_verified"])
        elif "custody_receipt" in custody_parity_report:
            receipt_verified = bool(custody_parity_report["custody_receipt"].get("verified", False))
        elif custody_parity_report.get("status") == "PASS":
            receipt_verified = True

        if not receipt_verified:
            custody_errors.append("Custody receipt is not verified")

        # Always treat explicit non-PASS status as blocking, independent of partial flags.
        status = custody_parity_report.get("status")
        if status is not None and status != "PASS":
            custody_errors.append(f"Custody parity status is {status}")

        # Honor explicit receipt validity when present.
        if "custody_receipt" in custody_parity_report and isinstance(custody_parity_report["custody_receipt"], dict):
            if custody_parity_report["custody_receipt"].get("valid") is False:
                custody_errors.append("Custody receipt is invalid")
                receipt_verified = False

    custody_ok = (len(custody_errors) == 0) and canonical_parity_ok and receipt_verified
    checks["custody_parity"] = {
        "passed": custody_ok,
        "canonical_parity_ok": canonical_parity_ok,
        "receipt_verified": receipt_verified,
        "errors": custody_errors,
    }

    ready = bool(manifest_ok and custody_ok)

    seal: dict[str, Any] = {
        "schema": RELEASE_SEAL_SCHEMA,
        "ready": ready,
        "checks": checks,
    }
    if isinstance(amalgamated_manifest, dict) and "digest" in amalgamated_manifest:
        seal["amalgamated_manifest_digest"] = amalgamated_manifest["digest"]

    payload_to_hash = {k: v for k, v in seal.items() if k not in ("seal_digest", "digest")}
    canonical_bytes = json.dumps(payload_to_hash, sort_keys=True).encode("utf-8")
    seal_digest = hashlib.sha256(canonical_bytes).hexdigest()

    seal["seal_digest"] = seal_digest
    seal["digest"] = seal_digest
    return seal
