#!/usr/bin/env python3
"""Screen the audio of exported Live Photo clips for speech, ENTIRELY LOCALLY (whisper.cpp; nothing leaves this Mac).

Why: a Live Photo's sound is often a person talking. Speech can carry names, numbers and private conversation that
the frames never show, and the playable lab plays every panel's sound at once. This pass finds which clips contain
speech so a policy (play / mute / exclude) can act on it. The lab's default policy is ``mute``: roughly a third to 43
percent of the clips that have audio contain speech.

Per clip it writes, under <root>/analysis/audio/ (private, mode 0600, never git, never served to a browser):
  <uuid>.json   {"screened", "has_audio", "speech", "words", "flags", "low_confidence"}   derived fields only
  <uuid>.txt    the raw transcript, kept for the owner's review; no tool reads it except this one
Transcripts are never printed. The log shows counts only.

Flags are cheap heuristics, not a classifier: ``number_sequence`` (digits spoken or written in a run of 6+),
``email_like``, ``introduces_self`` ("my name is", "I'm called"), ``possible_name`` (a capitalised word that is not at
a sentence start), ``long_speech`` (30+ words). Whisper invents text on silence and music, so known filler outputs
(for example "Thank you.") count as no speech and are marked ``low_confidence`` when only that survives.
Classifying what is SAID (hate, sexual content, threats) would need a text classifier; doing that with an API would
send transcripts off this Mac and needs the owner's separate consent, so it is deliberately not done here.

Inputs: <root>/analysis/tags/<uuid>.json (written by tag_clips.py) and <root>/originals/<uuid>/<uuid>.mov.
Incremental: clips that already have a record are skipped; --force screens them again; --limit N stops after N.

Run:  python3 -m tools.media.screen_audio --root /path/to/live-photos --model /path/to/ggml-base.en.bin
--root falls back to $SIMVLTANEA_LIVE_PHOTOS_ROOT and --model to $SIMVLTANEA_WHISPER_MODEL; there is no default path.
Needs ffmpeg, ffprobe and whisper-cli (whisper.cpp) on PATH; fetch_speech_model.py downloads the model.
Exit codes: 0 done, 2 a required tool, model or option is missing (one line, no traceback).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from tools.media.private_root import resolve_private_root

ROOT_ENV = "SIMVLTANEA_LIVE_PHOTOS_ROOT"
MODEL_ENV = "SIMVLTANEA_WHISPER_MODEL"
EXIT_MISSING = 2
UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")  # fullmatch only
MIN_WAV_BYTES = 3200  # 0.1 s of 16 kHz mono s16: anything shorter holds no speech
FILLERS = {"you", "thank you", "thanks", "bye", "thanks for watching", "thank you for watching", "yeah", "oh", "uh",
           "um", "hmm", "mm", "ah", "okay", "so", "the"}
ANNOTATION = re.compile(r"[\[\(\*][^\]\)\*]{0,60}[\]\)\*]")  # [BLANK_AUDIO] (music) *laughs*
DIGIT_WORDS = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
NOT_NAMES = {"The", "And", "But", "Yes"}


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True)


def has_audio(mov: pathlib.Path) -> bool:
    out = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type",
               "-of", "csv=p=0", str(mov)])
    return "audio" in out.stdout


def transcribe(mov: pathlib.Path, work: pathlib.Path, model: pathlib.Path) -> str | None:
    """The raw transcript, ``""`` when there is nothing to transcribe, ``None`` when whisper-cli failed."""
    wav = work / "a.wav"
    base = work / "t"
    result = run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(mov), "-vn", "-ac", "1", "-ar", "16000",
                  "-c:a", "pcm_s16le", str(wav)])
    if result.returncode != 0 or not wav.exists() or wav.stat().st_size < MIN_WAV_BYTES:
        return ""
    result = run(["whisper-cli", "-m", str(model), "-f", str(wav), "-nt", "-np", "-t", "2", "-otxt", "-of", str(base)])
    if result.returncode != 0:
        return None
    transcript = base.with_suffix(".txt")
    return transcript.read_text(errors="replace") if transcript.exists() else ""


def analyse(text: str) -> dict:
    """Derived fields of one transcript: speech verdict, word count, heuristic flags, low_confidence."""
    cleaned = " ".join(ANNOTATION.sub(" ", text).split())
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", cleaned)
    norm = re.sub(r"[^a-z ]", "", cleaned.lower()).strip()
    filler_only = norm in FILLERS or (len(words) <= 2 and all(w.lower().strip("'’-") in FILLERS for w in words))
    flags = []
    if re.search(r"\d{6,}|\d[\d\s().-]{8,}\d", cleaned) or \
            re.search(rf"(?:\b{DIGIT_WORDS}\b[\s,.-]*){{6,}}", cleaned.lower()):
        flags.append("number_sequence")
    if "@" in cleaned or re.search(r"\bat\b.{1,30}\bdot\s?(?:com|org|net|edu)\b", cleaned.lower()):
        flags.append("email_like")
    if re.search(r"\b(?:my name is|i'?m called|this is [A-Z][a-z]+ (?:speaking|here)|call me [A-Za-z]+)", cleaned, re.I):
        flags.append("introduces_self")
    sentence_starts = {m.end() for m in re.finditer(r"(?:^|[.!?]\s+)", cleaned)}
    for m in re.finditer(r"\b[A-Z][a-z]{2,}\b", cleaned):
        if m.start() not in sentence_starts and m.group(0) not in NOT_NAMES:
            flags.append("possible_name")
            break
    speech = len(words) >= 2 and not filler_only
    if speech and len(words) >= 30:
        flags.append("long_speech")
    return {"speech": speech, "words": len(words) if speech else 0, "flags": sorted(set(flags)) if speech else [],
            "low_confidence": bool(words) and filler_only}


def write_private(path: pathlib.Path, text: str) -> None:
    """Write ``text`` with mode 0600 (never wider, whatever the umask) by renaming a private temporary file."""
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(text)
    os.replace(temporary, path)


def missing_prerequisite(model: pathlib.Path | None) -> str | None:
    for tool in ("ffmpeg", "ffprobe", "whisper-cli"):
        if shutil.which(tool) is None:
            return f"{tool} not found on PATH" + (" (install whisper.cpp)" if tool == "whisper-cli" else "")
    if model is None:
        return f"no speech model given: pass --model or set {MODEL_ENV} (fetch_speech_model.py downloads one)"
    if not model.is_file():
        return "speech model file not found; run fetch_speech_model.py or fix --model"
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=pathlib.Path, default=os.environ.get(ROOT_ENV) or None,
                        help=f"private storage root (outside the checkout, or under var/); default ${ROOT_ENV}")
    parser.add_argument("--model", type=pathlib.Path, default=os.environ.get(MODEL_ENV) or None,
                        help=f"whisper.cpp ggml model file; default ${MODEL_ENV}")
    parser.add_argument("--limit", type=int, default=0, help="screen at most N clips this run (0 = all)")
    parser.add_argument("--force", action="store_true", help="screen clips that already have a record again")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.root is None:
        print(f"no --root given and ${ROOT_ENV} is not set", file=sys.stderr)
        return EXIT_MISSING
    if args.limit < 0:
        print("--limit must be >= 0", file=sys.stderr)
        return EXIT_MISSING
    root = resolve_private_root(args.root)
    problem = missing_prerequisite(args.model)
    if problem:
        print(problem, file=sys.stderr)
        return EXIT_MISSING
    out_dir = root / "analysis" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    done = failed = no_audio = speech = 0
    tally: dict[str, int] = {}
    for tag_file in sorted((root / "analysis" / "tags").glob("*.json")):
        uuid = tag_file.stem
        if not UUID_RE.fullmatch(uuid):
            continue
        target = out_dir / f"{uuid}.json"
        if target.exists() and not args.force:
            continue
        mov = root / "originals" / uuid / f"{uuid}.mov"
        if not mov.exists():
            continue
        if args.limit and done + failed >= args.limit:
            break
        if not has_audio(mov):
            write_private(target, json.dumps({"screened": True, "has_audio": False, "speech": False, "words": 0,
                                              "flags": [], "low_confidence": False}))
            no_audio += 1
            done += 1
            continue
        with tempfile.TemporaryDirectory(prefix="screen-audio-") as work:
            text = transcribe(mov, pathlib.Path(work), args.model)
        if text is None:
            failed += 1  # no marker is written, so the clip is retried next run
            continue
        result = analyse(text)
        write_private(out_dir / f"{uuid}.txt", text)
        write_private(target, json.dumps({"screened": True, "has_audio": True, **result}))
        done += 1
        speech += int(result["speech"])
        for flag in result["flags"]:
            tally[flag] = tally.get(flag, 0) + 1
        if done % 25 == 0:
            print(f"screened {done} (speech {speech}, no audio {no_audio}, failed {failed})", flush=True)
    print(f"audio screening: {done} clips screened this run | speech {speech} | no audio {no_audio} | "
          f"failed {failed} | flags {dict(sorted(tally.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
