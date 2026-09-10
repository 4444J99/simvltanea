"""Versioned, frame-addressed loop state compiled into the existing Triptych renderer.

No second encoder, browser runtime, archive recovery or generative audio is hidden here.
All time arithmetic is rational. Random selection is a stateless SHA-256 counter map.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ENGINE_VERSION = "1.0.0"
RNG = "sha256-counter-v1"
ORIENTATIONS = ("portrait", "landscape")
MAX_FRAMES = 14400
MAX_SEGMENTS = 1024
ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class StateError(ValueError):
    """Invalid state or a requested capability outside this version's contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StateError(message)


def keys(value: Any, allowed: set[str], required: set[str], where: str) -> None:
    require(isinstance(value, dict), f"{where} must be an object")
    require(not (value.keys() - allowed), f"{where}: unsupported fields {sorted(value.keys() - allowed)}")
    require(not (required - value.keys()), f"{where}: missing fields {sorted(required - value.keys())}")


def rational(value: Any, where: str) -> Fraction:
    require(type(value) in (str, int), f"{where} must be an integer or rational string, not a float")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
        raise StateError(f"{where}: invalid rational") from exc
    require(abs(result) <= 10**9 and result.denominator <= 10**9, f"{where}: out of bounds")
    return result


def integer(value: Any, low: int, high: int, where: str) -> None:
    require(type(value) is int and low <= value <= high, f"{where} must be an integer in {low}..{high}")


def identifier(value: Any, where: str) -> None:
    require(isinstance(value, str) and bool(ID.fullmatch(value)), f"{where}: invalid ID")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_state(state: dict, path: Path) -> None:
    validate_state(state)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_state(path: Path) -> dict:
    def unique(pairs: list) -> dict:
        obj = {}
        for key, value in pairs:
            require(key not in obj, f"duplicate JSON key: {key}")
            obj[key] = value
        return obj
    try:
        state = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"cannot read state: {exc}") from exc
    validate_state(state)
    return state


def rect_values(rect: Any) -> tuple[Fraction, ...]:
    require(isinstance(rect, list) and len(rect) == 4, "rect must be [x,y,width,height]")
    x, y, w, h = (rational(item, "rect") for item in rect)
    require(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1 and y + h <= 1,
            "rect must have positive area inside the unit canvas")
    return x, y, w, h


def validate_layouts(layouts: dict, loop_ids: set[str]) -> None:
    keys(layouts, set(ORIENTATIONS), set(ORIENTATIONS), "layouts")
    for orientation, layout in layouts.items():
        keys(layout, {"name", "cells"}, {"name", "cells"}, orientation)
        require(isinstance(layout["name"], str) and bool(layout["name"]), "layout name is required")
        require(isinstance(layout["cells"], list), "cells must be an array")
        seen, boxes = [], []
        for cell in layout["cells"]:
            keys(cell, {"loop", "rect", "fit", "focal"}, {"loop", "rect", "fit", "focal"}, "cell")
            identifier(cell["loop"], "cell.loop")
            seen.append(cell["loop"])
            require(cell["fit"] in ("contain", "cover"), "only contain/cover fit is implemented")
            require(isinstance(cell["focal"], list) and len(cell["focal"]) == 2, "focal needs two coordinates")
            require(all(0 <= rational(v, "focal") <= 1 for v in cell["focal"]), "focal must be in 0..1")
            box = rect_values(cell["rect"])
            x, y, w, h = box
            for a, b, c, d in boxes:
                require(not (x < a + c and a < x + w and y < b + d and b < y + h),
                        "overlapping/occluded panels are not supported in schema v1")
            boxes.append(box)
        require(len(seen) == len(loop_ids) and set(seen) == loop_ids,
                "each orientation must map every loop exactly once")


def validate_state(state: dict) -> None:
    fields = {"schema_version", "engine_version", "rng", "seed", "fps", "frames", "sources",
              "loops", "layouts", "events", "audio", "allow_source_reuse"}
    keys(state, fields, fields, "state")
    require(type(state["schema_version"]) is int and state["schema_version"] == SCHEMA_VERSION,
            "unsupported schema_version")
    require(state["engine_version"] == ENGINE_VERSION, "unsupported engine_version")
    require(state["rng"] == RNG, "unsupported randomness algorithm")
    require(type(state["seed"]) in (str, int), "seed must be a string or integer")
    integer(state["fps"], 1, 60, "fps")
    integer(state["frames"], 1, MAX_FRAMES, "frames")
    require(type(state["allow_source_reuse"]) is bool, "allow_source_reuse must be boolean")
    keys(state["audio"], {"mode", "routing", "generative"}, {"mode", "routing", "generative"}, "audio")
    require(state["audio"] == {"mode": "none", "routing": None, "generative": None},
            "versioned loop exports are silent in v1; legacy CLI retains none/panel/mix audio; "
            "generative audio and routing are not implemented")
    require(isinstance(state["sources"], list) and bool(state["sources"]), "sources must be a nonempty array")
    sources = {}
    for src in state["sources"]:
        keys(src, {"id", "path", "sha256", "kind", "duration"},
             {"id", "path", "sha256", "kind", "duration"}, "source")
        identifier(src["id"], "source.id")
        require(src["id"] not in sources, "duplicate source ID")
        require(isinstance(src["path"], str) and bool(src["path"]), "source path is required")
        path = Path(src["path"])
        require(not path.is_absolute() and ".." not in path.parts and ":" not in src["path"],
                "state source paths must be relative local paths without traversal or URLs")
        require(isinstance(src["sha256"], str) and bool(re.fullmatch(r"[0-9a-f]{64}", src["sha256"])),
                "source sha256 must be a lowercase digest")
        require(src["kind"] in ("video", "still"), "only video and still sources are implemented")
        require(rational(src["duration"], "source.duration") > 0, "source duration must be positive")
        if src["kind"] == "still":
            require(path.suffix.lower() in (".png", ".jpg", ".jpeg"), "still adapter supports PNG/JPEG only")
        sources[src["id"]] = src
    require(isinstance(state["loops"], list) and 1 <= len(state["loops"]) <= 32,
            "loop count must be 1..32 (resource guard, not a claim that every count is proven)")
    loop_ids = set()
    for loop in state["loops"]:
        keys(loop, {"id", "bank", "offset", "rate", "period", "epoch", "held", "trim"},
             {"id", "bank", "offset", "rate", "period", "epoch", "held"}, "loop")
        identifier(loop["id"], "loop.id")
        require(loop["id"] not in loop_ids, "duplicate loop ID")
        loop_ids.add(loop["id"])
        require(isinstance(loop["bank"], list) and bool(loop["bank"]), "bank must be an ordered nonempty array")
        require(all(isinstance(item, str) and item in sources for item in loop["bank"]), "bank references absent source")
        require(len(set(loop["bank"])) == len(loop["bank"]), "bank cannot repeat a source ID")
        require(rational(loop["offset"], "offset") >= 0, "offset must be nonnegative")
        require(0 < rational(loop["rate"], "rate") <= 8, "rate must be in (0,8]")
        require(rational(loop["period"], "period") > 0, "selection period must be positive")
        integer(loop["epoch"], 0, 2**31 - 1, "epoch")
        require(type(loop["held"]) is bool, "held must be boolean")
        if "trim" in loop:
            require(isinstance(loop["trim"], list) and len(loop["trim"]) == 2, "trim needs in/out bounds")
            low, high = (rational(v, "trim") for v in loop["trim"])
            require(0 <= low < high, "trim must have positive duration")
            require(all(high <= rational(sources[s]["duration"], "duration") for s in loop["bank"]),
                    "trim exceeds a bank source duration")
    validate_layouts(state["layouts"], loop_ids)
    require(isinstance(state["events"], list), "events must be an array")
    previous = -1
    for event in state["events"]:
        require(isinstance(event, dict), "event must be an object")
        op = event.get("op")
        extra = {"hold": {"loop", "value"}, "reroll": {"loop"},
                 "swap": {"a", "b"}, "move": {"loop", "orientation", "rect"}}
        require(isinstance(op, str) and op in extra, f"unsupported event: {op}")
        fields = {"op", "frame"} | extra[op]
        keys(event, fields, fields, "event")
        integer(event["frame"], 0, state["frames"] - 1, "event.frame")
        require(event["frame"] >= previous, "events must be ordered; equal frames use array order")
        previous = event["frame"]
        for key in ("loop", "a", "b"):
            if key in event:
                require(isinstance(event[key], str) and event[key] in loop_ids, f"event references absent loop: {event[key]}")
        if op == "hold":
            require(type(event["value"]) is bool, "hold.value must be boolean")
        elif op == "swap":
            require(event["a"] != event["b"], "swap requires two different loops")
        elif op == "move":
            require(event["orientation"] in ORIENTATIONS, "move requires an orientation")
            rect_values(event["rect"])
    # Catch event-induced collisions, invalid trims and unsupported overlap before encoding.
    for frame in sorted({0, *(event["frame"] for event in state["events"])}):
        resolved = resolve_at(state, frame)
        validate_layouts(resolved["layouts"], loop_ids)


def media_paths(state: dict, root: Path, verify: bool = True) -> dict[str, Path]:
    root = root.resolve()
    paths = {}
    for src in state["sources"]:
        path = (root / src["path"]).resolve()
        require(path.is_relative_to(root), "media symlink escapes state root")
        require(path.is_file(), f"absent media: {src['id']}")
        if verify:
            require(sha256_file(path) == src["sha256"], f"media hash mismatch: {src['id']}")
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height,codec_name,duration", "-of", "json", str(path)],
                                   check=True, capture_output=True, text=True)
            streams = json.loads(probe.stdout).get("streams", [])
            require(bool(streams) and streams[0].get("width", 0) > 0, f"no video/image stream: {src['id']}")
            if src["kind"] == "still":
                require(streams[0].get("codec_name") in ("png", "mjpeg"), "still codec must be PNG/JPEG")
            elif streams[0].get("duration") not in (None, "N/A"):
                actual = Fraction(streams[0]["duration"])
                require(abs(actual - rational(src["duration"], "duration")) <= Fraction(1, state["fps"]),
                        f"declared video duration disagrees with probe: {src['id']}")
        paths[src["id"]] = path
    return paths


def local_time(loop: dict, frame: int, fps: int) -> Fraction:
    elapsed = Fraction(0) if loop["held"] else Fraction(frame - loop["anchor"], fps) * rational(loop["rate"], "rate")
    return rational(loop["offset"], "offset") + elapsed


def choose_source(state: dict, loop: dict, frame: int) -> str:
    if loop.get("pin") is not None:
        return loop["pin"]
    cycle = int(local_time(loop, frame, state["fps"]) // rational(loop["period"], "period"))
    payload = [RNG, state["seed"], loop["id"], loop["epoch"], cycle, loop["bank"]]
    value = int.from_bytes(hashlib.sha256(canonical_json(payload).encode("utf-8")).digest(), "big")
    return loop["bank"][value % len(loop["bank"])]


def resolve_at(state: dict, frame: int) -> dict:
    """Pure replay from the saved initial state; never consults wall clock or call order."""
    integer(frame, 0, state["frames"], "frame")
    loops = {item["id"]: dict(copy.deepcopy(item), anchor=0, pin=None) for item in state["loops"]}
    layouts = copy.deepcopy(state["layouts"])
    for event in state["events"]:
        at = event["frame"]
        if at > frame:
            break
        op = event["op"]
        if op == "hold":
            loop = loops[event["loop"]]
            loop["offset"] = str(local_time(loop, at, state["fps"]))
            loop["anchor"], loop["held"] = at, event["value"]
        elif op == "reroll":
            loop = loops[event["loop"]]
            loop["epoch"] += 1
            loop["pin"] = None
        elif op == "swap":
            a, b = loops[event["a"]], loops[event["b"]]
            a["pin"], b["pin"] = choose_source(state, b, at), choose_source(state, a, at)
        elif op == "move":
            for cell in layouts[event["orientation"]]["cells"]:
                if cell["loop"] == event["loop"]:
                    cell["rect"] = list(event["rect"])
    sources = {src["id"]: src for src in state["sources"]}
    resolved = []
    for loop in loops.values():
        source_id = choose_source(state, loop, frame)
        src = sources[source_id]
        local = local_time(loop, frame, state["fps"])
        low, high = (rational(x, "trim") for x in loop.get("trim", [0, src["duration"]]))
        require(high <= rational(src["duration"], "duration"), "swapped source does not fit loop trim")
        offset = Fraction(0) if src["kind"] == "still" else low + local % (high - low)
        resolved.append({"id": loop["id"], "source": source_id, "kind": src["kind"],
                         "local": str(local), "source_offset": str(offset),
                         "rate": str(rational(loop["rate"], "rate")), "held": loop["held"],
                         "epoch": loop["epoch"]})
    if not state["allow_source_reuse"]:
        require(len({x["source"] for x in resolved}) == len(resolved)
                and len({sources[x["source"]]["sha256"] for x in resolved}) == len(resolved),
                "source reuse must be explicit; no duplicated IDs or media bytes as filler")
    return {"frame": frame, "loops": resolved, "layouts": layouts}


def orientation_for(width: int, height: int) -> str:
    require(type(width) is int and type(height) is int and width > 0 and height > 0,
            "viewport dimensions must be positive integers")
    return "landscape" if width >= height else "portrait"


def presentation_at(state: dict, frame: int, width: int, height: int) -> dict:
    resolved = resolve_at(state, frame)
    return {"frame": frame, "loops": resolved["loops"],
            "layout": resolved["layouts"][orientation_for(width, height)]}


def pixel_placements(layout: dict, width: int, height: int) -> tuple:
    from render_triptych import Placement
    def edge(value: Fraction, dimension: int) -> int:
        return 2 * round(value * dimension / 2)
    result = []
    for cell in layout["cells"]:
        x, y, w, h = rect_values(cell["rect"])
        a, b = edge(x, width), edge(y, height)
        c, d = edge(x + w, width), edge(y + h, height)
        require(c > a and d > b, "panel collapsed at this export resolution")
        result.append(Placement(cell["loop"], a, b, c - a, d - b, cell["fit"],
                                tuple(float(rational(v, "focal")) for v in cell["focal"])))
    return tuple(result)


def continuous(previous: dict, current: dict, fps: int, orientation: str) -> bool:
    if previous["layouts"][orientation] != current["layouts"][orientation]:
        return False
    for a, b in zip(previous["loops"], current["loops"]):
        if any(a[k] != b[k] for k in ("id", "source", "kind", "rate", "held")):
            return False
        delta = Fraction(0) if a["held"] or a["kind"] == "still" else Fraction(a["rate"]) / fps
        if Fraction(b["source_offset"]) != Fraction(a["source_offset"]) + delta:
            return False
    return True


def compile_segments(state: dict, root: Path, orientation: str, width: int, height: int,
                     verify_media: bool = True) -> list:
    from render_triptych import Panel, Segment
    validate_state(state)
    require(orientation in ORIENTATIONS, "unknown orientation")
    require(orientation_for(width, height) == orientation, "export dimensions disagree with orientation")
    require(width % 2 == 0 and height % 2 == 0, "H.264 export dimensions must be even")
    require(width * height <= 3840 * 2160, "export exceeds the 4K pixel resource guard")
    paths = media_paths(state, root, verify_media)
    sources = {src["id"]: src for src in state["sources"]}
    starts = [(0, resolve_at(state, 0))]
    previous = starts[0][1]
    for frame in range(1, state["frames"]):
        current = resolve_at(state, frame)
        if not continuous(previous, current, state["fps"], orientation):
            starts.append((frame, current))
        previous = current
    require(len(starts) <= MAX_SEGMENTS, "composition exceeds segment resource guard; no panels were removed")
    segments = []
    for index, (frame, snapshot) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else state["frames"]
        panels = tuple(Panel(loop["id"], None, paths[loop["source"]], float(Fraction(loop["source_offset"])),
                             float(Fraction(sources[loop["source"]]["duration"])), False,
                             loop["kind"], float(Fraction(loop["rate"])), loop["held"], True)
                       for loop in snapshot["loops"])
        segments.append(Segment(index, frame / state["fps"], (end - frame) / state["fps"], panels,
                                pixel_placements(snapshot["layouts"][orientation], width, height)))
    return segments


def from_authoring_model(composition: Any, source_map: dict[str, dict], frames: int = 144,
                         fps: int = 24) -> dict:
    """Adapt PR #9's 0.1.0 initial, resolved-source authoring snapshot.

    Existing geometry and clocks are preserved; float inputs are rounded to nine
    decimal places before exact rational conversion. This does NOT translate the
    old implicit random.Random bank selection or an already-applied event history.
    Such requests fail rather than silently claim replay compatibility.
    """
    composition.validate()
    require(composition.engine_version == "0.1.0", "unsupported authoring model version")
    require(not composition.event_history, "authoring adapter requires an initial snapshot without event history")
    require(all(not loop.audible and loop.held_at is None and loop.reroll_index == 0
                for loop in composition.loops), "authoring adapter requires unheld, silent resolved sources")
    def exact(value: float) -> str:
        return str(Fraction(str(round(value, 9))))
    sources, loops = {}, []
    for loop in composition.loops:
        require(loop.source in source_map, "authoring source has no hashed media binding")
        source = copy.deepcopy(source_map[loop.source])
        sources[source["id"]] = source
        item = dict(id=loop.id, bank=[source["id"]], offset=exact(loop.offset),
                    rate=exact(loop.rate), period=source["duration"], epoch=0, held=False)
        if loop.trim_in or loop.trim_out is not None:
            item["trim"] = [exact(loop.trim_in), exact(loop.trim_out) if loop.trim_out is not None else source["duration"]]
        loops.append(item)
    layouts = {}
    for layout in composition.layouts:
        # Cells are serialized back-to-front; stable sorting preserves the old
        # equal-z fixture order. This is draw order, not permission for overlap.
        ordered = sorted(layout.placements, key=lambda p: p.z)
        require(layout.orientation not in layouts, "duplicate orientation in authoring model")
        layouts[layout.orientation] = dict(name=layout.id, cells=[
            dict(loop=p.loop_id, rect=[exact(v) for v in (p.x,p.y,p.width,p.height)],
                 fit=p.fit, focal=[exact(p.focal_x),exact(p.focal_y)]) for p in ordered])
    state = dict(schema_version=SCHEMA_VERSION,engine_version=ENGINE_VERSION,rng=RNG,
                 seed=composition.seed,fps=fps,frames=frames,allow_source_reuse=False,
                 sources=list(sources.values()),loops=loops,layouts=layouts,events=[],
                 audio=dict(mode="none",routing=None,generative=None))
    validate_state(state)
    return state


def render_from_args(args: Any) -> int:
    """CLI adapter; encoding and concatenation remain in render_triptych.py."""
    import render_triptych as engine
    try:
        incompatible = ("input_dir", "manifest", "timing", "phrase", "layout", "panel_order", "max_videos",
                        "max_clip_seconds", "audio", "audio_panel", "audio_gain", "audio_left_gain",
                        "audio_middle_gain", "audio_right_gain", "audio_fade", "direction", "tone",
                        "tone_strength", "tone_smoothing", "fps")
        require(not any(getattr(args, key, None) is not None for key in incompatible),
                "--state owns timing/content/audio/fps; legacy overrides cannot be mixed with it")
        require(args.orientation is not None, "--state export requires explicit --orientation")
        state_path = args.state.resolve()
        state = load_state(state_path)
        require((args.width is None) == (args.height is None), "provide both width and height")
        width, height = ((1080, 1920) if args.orientation == "portrait" else (1920, 1080))
        if args.width is not None:
            width, height = args.width, args.height
        # Obtain historical defaults through the existing parser/settings builder.
        defaults = copy.copy(args)
        defaults.width, defaults.height = 1080, 1920
        settings = engine.build_settings(defaults)
        output = args.output.resolve() if args.output else state_path.parent / f"{state_path.stem}-{args.orientation}.mp4"
        require(engine.path_inside(output, engine.SCRIPT_DIR), "output must remain inside the incubator")
        settings = replace(settings, width=width, height=height, fps=state["fps"], output_file=output)
        segments = compile_segments(state, state_path.parent, args.orientation, width, height)
        if args.dry_run:
            print(canonical_json({"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
                                  "segments": len(segments), "frames": state["frames"],
                                  "loops": len(state["loops"]), "orientation": args.orientation}))
            return 0
        engine.render(segments, settings)
        print(f"wrote {output}")
        return 0
    except (StateError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"composition: {exc}") from exc
