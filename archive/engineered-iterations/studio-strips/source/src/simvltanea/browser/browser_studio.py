#!/usr/bin/env python3
"""Stage the SIMVLTANEA web studio: a static page that plays a visitor's own loops.

The studio is client-only. A visitor picks a layout family (strips by default,
authored, or their own layout file) and a panel count, then drops one video loop
per panel; the page checks, hashes and compiles them in the browser and plays them
at once on independent clocks in the family's portrait or landscape layout. The
families and the counts each offers come from ``layouts.json``, the
``simvltanea.layout-bundle/2`` that ``layout_bundle_v2()`` builds. Files never leave
the device. ``stage_studio(output)`` writes the flat, relative-URL site::

    index.html  runtime.js  compiler.js  studio.js  layouts.json

The HTML shell lives here as a string constant because HTML and CSS files are
not permitted under ``src/``. Staging is deterministic and touches no network,
media or subprocess, so the same sources always yield the same bytes::

    python -m simvltanea.browser.browser_studio --output var/site/studio
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from simvltanea.browser.layout_bundle import layout_bundle_v2

HERE = Path(__file__).resolve().parent
STUDIO_TITLE = 'SIMVLTANEA studio: your loops, playing at once'
STUDIO_FILES = ('index.html', 'runtime.js', 'compiler.js', 'studio.js', 'layouts.json')

STYLE = '''
:root{color-scheme:dark;--bg:#0d0d0d;--fg:#f2f2f2;--muted:#bdbdbd;--line:#4a4a4a;--accent:#ffd54a;--panel:#1b1b1b}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
[hidden]{display:none!important}
#setup{max-width:46rem;margin:0 auto;padding:1.25rem 1rem 3rem}
h1{font-size:1.65rem;line-height:1.2;margin:.5rem 0 .75rem;letter-spacing:.03em}
h2{font-size:1.15rem;margin:1.75rem 0 .25rem}
p{margin:.5rem 0}
.privacy{border-left:4px solid var(--accent);padding:.5rem .75rem;background:var(--panel)}
.drop{margin:1.25rem 0;padding:1.5rem 1rem;border:2px dashed var(--line);border-radius:.75rem;text-align:center}
.drop.over{border-color:var(--accent);background:#262626}
button,.button{font:inherit;color:#111;background:var(--fg);border:2px solid var(--fg);border-radius:.4rem;
padding:.5rem 1rem;min-height:44px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
button:disabled{opacity:.45;cursor:not-allowed}
:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
#files:focus-visible+label{outline:3px solid var(--accent);outline-offset:3px}
#files:disabled+label{opacity:.45;cursor:not-allowed}
.visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;
clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0}
.hint{color:var(--muted);font-size:.9rem}
#refusals{color:#ffb8ab;padding-left:1.25rem}
#refusals:empty{display:none}
#loops{padding-left:1.75rem;margin:.5rem 0}
#loops li{padding:.6rem 0;border-bottom:1px solid var(--line)}
.loop-name{display:block;font-weight:600;overflow-wrap:anywhere}
.loop-facts{display:block;color:var(--muted);font-size:.9rem}
.loop-actions{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.4rem}
.loop-actions button{min-height:40px;padding:.25rem .75rem;color:var(--fg);background:transparent;border-color:var(--line)}
#start{margin-top:1rem;font-weight:700;background:var(--accent);border-color:var(--accent)}
#player{position:fixed;inset:0;display:flex;flex-direction:column;background:#000}
#frame{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;container-type:size}
#stage{position:relative;width:100%;height:100%;overflow:hidden;background:#000}
#player[data-orientation=portrait] #stage{width:min(100cqw,calc(100cqh * 9 / 16));height:min(100cqh,calc(100cqw * 16 / 9))}
#player[data-orientation=landscape] #stage{width:min(100cqw,calc(100cqh * 16 / 9));height:min(100cqh,calc(100cqw * 9 / 16))}
#stage:focus-visible{outline:3px solid var(--accent);outline-offset:-3px}
.loop{position:absolute;overflow:hidden;background:#000}
.loop video,.loop img{width:100%;height:100%;display:block}
#bar{display:flex;flex-wrap:wrap;align-items:center;gap:.35rem .6rem;background:#111;border-top:1px solid #333;
padding:.4rem .6rem calc(.4rem + env(safe-area-inset-bottom))}
#bar button{min-height:40px;padding:.25rem .8rem}
#bar fieldset{display:flex;flex-wrap:wrap;align-items:center;gap:.1rem .6rem;border:0;margin:0;padding:0}
#bar legend{float:left;padding:0;margin-right:.2rem;color:var(--muted)}
#bar label{display:inline-flex;align-items:center;gap:.3rem;min-height:40px}
#bar input{width:1.1rem;height:1.1rem;margin:0;accent-color:var(--accent)}
#runtime-status{flex:1 1 14rem;margin:0;font-size:.85rem;color:var(--muted)}
#layout{border:1px solid var(--line);border-radius:.75rem;margin:1.25rem 0 0;padding:.5rem 1rem 1rem}
#layout legend{padding:0 .35rem;font-weight:600}
#families{display:flex;flex-wrap:wrap;gap:.25rem 1.25rem}
#families label,.panels{display:inline-flex;align-items:center;gap:.45rem;min-height:44px}
#families input{width:1.15rem;height:1.15rem;margin:0;accent-color:var(--accent)}
#panels{font:inherit;min-height:44px;min-width:4.5rem;padding:.25rem .5rem;color:var(--fg);background:var(--panel);
border:2px solid var(--line);border-radius:.4rem}
.layout-file{margin-top:.5rem}
#layout-file:focus-visible+label{outline:3px solid var(--accent);outline-offset:3px}
.layout-file label.button{color:var(--fg);background:transparent;border-color:var(--line)}
#layout-error{color:#ffb8ab}
#layout-error:empty,#layout-status:empty{display:none}
@media (max-width:30rem){#setup{padding-top:.75rem}h1{font-size:1.4rem}#bar{gap:.25rem .45rem}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important;
scroll-behavior:auto!important}}
'''
STYLE_HASH = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
# Same-origin scripts and layouts.json only; the chosen files play from blob: URLs.
CONTENT_SECURITY_POLICY = ("default-src 'none'; script-src 'self'; connect-src 'self'; media-src blob:; "
                           f"img-src blob:; style-src 'sha256-{STYLE_HASH}'; base-uri 'none'; form-action 'none'")

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="''' + CONTENT_SECURITY_POLICY + '''">
<meta name="referrer" content="no-referrer">
<meta name="description" content="Play your own video loops at once, one per panel, on this device.">
<title>''' + STUDIO_TITLE + '''</title>
<style>''' + STYLE + '''</style>
</head>
<body>
<main id="studio" data-view="setup">
<section id="setup" aria-labelledby="studio-title">
<h1 id="studio-title">SIMVLTANEA studio</h1>
<p>Pick a layout and a number of panels, then choose one short video loop per panel and watch them play at the
same time, each repeating on its own clock. Every panel is one of your loops, never filler or a copy.</p>
<p class="privacy"><strong>Your videos never leave this device.</strong> Nothing is uploaded: this page reads, checks and
plays the files inside your browser.</p>
<fieldset id="layout">
<legend>Layout</legend>
<div id="families" role="radiogroup" aria-label="Layout family"></div>
<label class="panels" for="panels">Panels <select id="panels"></select></label>
<p class="hint">Strips fill the screen edge to edge with one band per loop, zoomed in more the fewer
panels there are. Authored layouts are the hand-placed engineering pairs.</p>
<div class="layout-file">
<input id="layout-file" class="visually-hidden" type="file" accept=".json,application/json">
<label for="layout-file" class="button">Use my own layout file</label>
<p class="hint">A layout preset or layout pair JSON file. It is read on this device and never uploaded.</p>
</div>
<p id="layout-status" role="status" aria-live="polite"></p>
<p id="layout-error" role="alert"></p>
</fieldset>
<div id="drop" class="drop">
<p>Drop video files here, or</p>
<input id="files" class="visually-hidden" type="file" multiple accept="video/*,.mov,.mp4,.m4v,.webm">
<label for="files" class="button">Choose videos</label>
<p class="hint">MP4 or QuickTime MOV with H.264, or HEVC where this browser can play it.
Sound is never played. Up to 512 MiB in total.</p>
</div>
<p id="progress" role="status" aria-live="polite"></p>
<ul id="refusals" aria-label="Files not added" aria-live="polite"></ul>
<h2 id="loops-title">Your loops</h2>
<p id="count" role="status" aria-live="polite">No loops chosen yet.</p>
<ol id="loops" aria-labelledby="loops-title"></ol>
<button id="start" type="button" disabled>Play these loops</button>
<p id="length" class="hint"></p>
<p id="runtime-note" class="hint"></p>
</section>
<section id="player" aria-label="Playback" data-orientation="auto" hidden>
<div id="frame"><div id="stage" role="region" aria-label="Your loops, playing at once"></div></div>
<div id="bar" role="group" aria-label="Playback controls">
<button id="toggle" type="button" aria-label="Play">Play</button>
<button id="restart" type="button">Restart</button>
<fieldset id="orientation"><legend>Layout</legend>
<label><input type="radio" name="orientation" value="auto" checked>Auto</label>
<label><input type="radio" name="orientation" value="portrait">Portrait</label>
<label><input type="radio" name="orientation" value="landscape">Landscape</label>
</fieldset>
<label><input id="repeat" type="checkbox" checked>Auto-repeat</label>
<button id="change" type="button">Change loops</button>
<p id="runtime-status" role="status" aria-live="polite">Choose loops to begin.</p>
</div>
</section>
</main>
<script src="compiler.js" defer></script>
<script src="studio.js" defer></script>
<script src="runtime.js" defer></script>
</body>
</html>
'''


class StudioStagingError(ValueError):
    """The output directory cannot safely receive the studio."""


def studio_files() -> dict[str, bytes]:
    """Return the exact bytes of every staged file, keyed by its flat name."""
    layouts = json.dumps(layout_bundle_v2(), indent=2, ensure_ascii=False) + '\n'
    return {
        'index.html': INDEX_HTML.encode(),
        'runtime.js': (HERE / 'browser.runtime.js').read_bytes(),
        'compiler.js': (HERE / 'browser.compiler.js').read_bytes(),
        'studio.js': (HERE / 'browser.studio.js').read_bytes(),
        'layouts.json': layouts.encode(),
    }


def stage_studio(output: Path) -> None:
    """Write the flat studio into ``output``, creating it when absent.

    Only the five studio files are ever written. A directory holding anything
    else (including hidden files, subdirectories or symlinks) is refused before
    any byte is written, so staging cannot clobber or mix with foreign content.
    """
    output = Path(output)
    if output.is_symlink():
        raise StudioStagingError(f'studio output must not be a symlink: {output}')
    if output.exists() and not output.is_dir():
        raise StudioStagingError(f'studio output is not a directory: {output}')
    files = studio_files()
    if output.exists():
        foreign = sorted(entry.name for entry in output.iterdir()
                         if entry.name not in files or entry.is_symlink() or not entry.is_file())
        if foreign:
            raise StudioStagingError(
                f'studio output {output} contains entries stage_studio does not own: {", ".join(foreign)}; '
                'choose an empty directory or one holding only a previous studio')
    output.mkdir(parents=True, exist_ok=True)
    for name in STUDIO_FILES:
        target = output / name
        if not target.is_file() or target.read_bytes() != files[name]:
            target.write_bytes(files[name])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, required=True, help='directory to receive the flat studio')
    args = parser.parse_args(argv)
    stage_studio(args.output)
    print(f'studio staged: {", ".join(STUDIO_FILES)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
