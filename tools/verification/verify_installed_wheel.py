"""Verify a wheel in a fresh consumer environment outside the source checkout.

The consumer receives no editable install, source PYTHONPATH, user site, or
verification extras. It generates only synthetic media. A successful receipt
proves this bounded package/render path, not browser playback or artistic/media
acceptance. FFmpeg and ffprobe are explicit external system prerequisites.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import venv


CONSUMER = r'''
import hashlib
from importlib import metadata, resources, util
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import simvltanea
from simvltanea.authoring import build_artifact001, composition as c
from simvltanea.browser import build_preview
from simvltanea.paths import REPO_ROOT, PROOFS_DIR

workspace = Path.cwd().resolve()
package = Path(simvltanea.__file__).resolve()
assert package.is_relative_to(Path(sys.prefix).resolve()), "package is not installed in the isolated venv"
assert REPO_ROOT == workspace, "installed package resolved a source checkout instead of its caller workspace"
assert all(util.find_spec(name) is None for name in ("PIL", "pytest", "playwright")), "verification extras leaked into consumer"
for entry in sys.path:
    assert not (Path(entry) / "pyproject.toml").is_file(), "a checkout is on the consumer import path"
assets = {}
for module, names in (("simvltanea", ("layout.toml", "py.typed")),
                      ("simvltanea.browser", ("browser.runtime.js", "browser.continuity.js"))):
    for name in names:
        data = resources.files(module).joinpath(name).read_bytes()
        assets[module + ":" + name] = hashlib.sha256(data).hexdigest()
layout = tomllib.loads(resources.files("simvltanea").joinpath("layout.toml").read_text())
root = PROOFS_DIR / "consumer"
(root / "media").mkdir(parents=True)
source_map = {}
for number, pattern in enumerate(("testsrc2", "smptebars"), 1):
    target = root / "media" / f"source-{number}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                    f"{pattern}=size=160x160:rate=24", "-t", "2", "-an", "-c:v", "libx264",
                    "-threads", "1", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(target)],
                   check=True, timeout=60)
    source_map[f"fixtures/loop-{number}.mp4"] = dict(
        id=f"source-{number}", path=f"media/source-{number}.mp4", kind="video",
        duration="2", sha256=c.sha256_file(target))
state = c.from_authoring_model(build_artifact001(2), source_map, frames=24, fps=24)
state_path = root / "state.json"
c.save_state(state, state_path)
plan = build_preview(state_path, root / "preview")
assert len(plan["tracks"]) == 2
assert (root / "preview" / "runtime.js").read_bytes() == resources.files("simvltanea.browser").joinpath("browser.runtime.js").read_bytes()
assert c.presentation_at(state, 12, 320, 180)["loops"] == c.presentation_at(state, 12, 180, 320)["loops"]
outputs = []
for orientation, width, height in (("portrait", 180, 320), ("landscape", 320, 180)):
    output = root / (orientation + ".mp4")
    subprocess.run([sys.executable, "-I", "-m", "simvltanea.render_triptych", "--state", str(state_path),
                    "--orientation", orientation, "--output", str(output), "--width", str(width),
                    "--height", str(height), "--preset", "ultrafast", "--crf", "30"],
                   check=True, timeout=120)
    facts = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_frames", "-of", "json", str(output)],
                      check=True, capture_output=True, text=True, timeout=30).stdout)
    stream = facts["streams"][0]
    assert (stream["codec_name"], stream["pix_fmt"], stream["width"], stream["height"], int(stream["nb_frames"])) == ("h264", "yuv420p", width, height, 24)
    outputs.append(dict(orientation=orientation, sha256=c.sha256_file(output), stream=stream))
result = dict(package_version=metadata.version("simvltanea"), python=sys.version,
              installed_in_venv=True, caller_workspace=True, verification_extras_absent=True,
              layout_contract=layout["contract"]["version"], packaged_assets=assets,
              loop_count=2, frames=24, preview_compilation=True, orientation_model_identity=True,
              ffmpeg=subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0],
              renders=outputs)
Path("consumer-result.json").write_text(json.dumps(result, indent=2) + "\n")
'''


def sanitized_environment() -> dict[str, str]:
    """Remove Python/source-root overrides rather than inheriting host imports."""
    blocked = {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "SIMVLTANEA_ROOT", "SIMVLTANEA_LAYOUT"}
    result = {key: value for key, value in os.environ.items() if key not in blocked}
    result["PYTHONNOUSERSITE"] = "1"
    return result


def verify(wheel: Path, checkout: Path) -> dict:
    wheel = wheel.resolve(strict=True)
    if wheel.suffix != ".whl" or not wheel.is_file():
        raise ValueError("--wheel must be a built wheel file")
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"missing required system executable: {executable}")
    env = sanitized_environment()
    with tempfile.TemporaryDirectory(prefix="simvltanea-consumer-") as temporary:
        base = Path(temporary).resolve()
        if base.is_relative_to(checkout.resolve()):
            raise ValueError("consumer temporary directory must be outside the checkout")
        environment, workspace = base / "venv", base / "workspace"
        workspace.mkdir()
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                       cwd=workspace, env=env, check=True, timeout=120)
        subprocess.run([str(python), "-I", "-m", "pip", "check"],
                       cwd=workspace, env=env, check=True, timeout=60)
        script = workspace / "consumer.py"
        script.write_text(CONSUMER, encoding="utf-8")
        subprocess.run([str(python), "-I", str(script)], cwd=workspace, env=env, check=True, timeout=360)
        return json.loads((workspace / "consumer-result.json").read_text())


def main() -> int:
    from tools.paths import PROOFS_DIR, REPO_ROOT, require_in_var
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    target = require_in_var(args.receipt or PROOFS_DIR / "installed-wheel" / ("run-" + uuid.uuid4().hex) / "receipt.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit("receipt already exists; preserve dated evidence and choose a new path")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt = dict(schema="simvltanea.installed-wheel-proof.v1", observed_at=datetime.now(timezone.utc).isoformat(),
                   tested_git_head=head, success=False,
                   limitations=["Synthetic two-loop engineering proof only", "Preview compilation is not live browser playback",
                                "No personal-media custody, historical fidelity, target-device or artist approval",
                                "System packages, Python patch version and build dependency inputs are not fully immutable"])
    try:
        wheel = args.wheel.resolve(strict=True)
        receipt["wheel"] = dict(name=wheel.name, bytes=wheel.stat().st_size,
                                sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
        receipt["consumer"] = verify(wheel, REPO_ROOT)
        receipt["success"] = True
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        receipt["error"] = str(exc)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(success=receipt["success"], receipt=str(target.relative_to(REPO_ROOT)))))
    return 0 if receipt["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
