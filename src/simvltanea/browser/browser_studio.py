#!/usr/bin/env python3
"""Stage the SIMVLTANEA web studio: a static page of loops on their own clocks.

The studio is client-only and plays on load: built-in generative loops, recorded
in the browser, in a random family, panel count and order (``?seed=`` repeats a
roll), with each loop's own sound once the visitor first touches the page. A
visitor may drop their own videos (or a layout file); the page checks, hashes and
compiles them in the browser. The families and the counts each offers come from
``layouts.json``, the ``simvltanea.layout-bundle/2`` that ``layout_bundle_v2()``
builds. Files never leave the device. ``stage_studio(output)`` writes the flat, relative-URL site::

    index.html  runtime.js  compiler.js  studio.js  layouts.json
    lab.html  lab_model.js  lab_engine.js  lab_ui.js  lab_audio.js

A public clip library (``library/manifest.json`` and ``library/clips/``) is added
beside these at deploy time by ``tools.publishing.stage_library_site``, never here.

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
from simvltanea.browser.browser_lab import LAB_FILES, lab_files

HERE = Path(__file__).resolve().parent
STUDIO_TITLE = 'SIMVLTANEA studio: loops on their own clocks'
STUDIO_FILES = ('index.html', 'runtime.js', 'compiler.js', 'studio.js', 'layouts.json', *LAB_FILES)

STYLE = '''
:root{color-scheme:dark;--bg:#0a0a0b;--fg:rgba(255,255,255,.88);--dim:rgba(255,255,255,.55);
--glass:rgba(20,20,23,.52);--edge:rgba(255,255,255,.09);--ease:cubic-bezier(.2,.7,.2,1)}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);color:var(--fg);
font:15px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
[hidden]{display:none!important}
.visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;
clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap;border:0}
#studio{position:fixed;inset:0}
#studio.idle{cursor:none}
#frame,#stage,#preview,#ghost{position:absolute;inset:0}
#frame{z-index:0}
#bar,#corner,#start,#toast,#about,#drop{z-index:2}
#stage{overflow:hidden;background:#000}
#stage:focus-visible{outline:none}
#preview,#ghost{pointer-events:none;opacity:0;transition:opacity 220ms var(--ease)}
#preview.on,#ghost.on{opacity:1}
#ghost.on{transition:none}
.loop{position:absolute;overflow:hidden;background:#000}
.loop video,.loop img,.loop canvas{width:100%;height:100%;display:block}
#preview canvas{object-fit:cover}
#bar,#corner{position:fixed;display:flex;align-items:center;gap:2px;padding:5px;border-radius:999px;
background:var(--glass);border:1px solid var(--edge);box-shadow:0 10px 40px rgba(0,0,0,.35);
-webkit-backdrop-filter:blur(18px) saturate(150%);backdrop-filter:blur(18px) saturate(150%);
transition:opacity 240ms var(--ease),transform 240ms var(--ease)}
#bar{left:50%;bottom:calc(16px + env(safe-area-inset-bottom));transform:translateX(-50%);width:max-content;
max-width:calc(100vw - 12px)}
#corner{top:calc(14px + env(safe-area-inset-top));right:calc(14px + env(safe-area-inset-right))}
.idle #bar{opacity:0;transform:translate(-50%,10px);pointer-events:none}
.idle #corner{opacity:0;transform:translateY(-10px);pointer-events:none}
.sep{width:1px;height:22px;margin:0 4px;background:var(--edge)}
button{font:inherit;color:var(--fg);background:transparent;border:0;border-radius:999px;width:44px;height:44px;flex:none;
padding:0;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;position:relative;
transition:background-color 160ms var(--ease),color 160ms var(--ease),opacity 160ms var(--ease)}
button:hover{background:rgba(255,255,255,.1);color:#fff}
button:active{background:rgba(255,255,255,.16)}
button:disabled{opacity:.3;cursor:default;background:transparent}
button svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
:focus-visible{outline:2px solid #fff;outline-offset:2px}
#play svg .fill,#start svg .fill{fill:currentColor;stroke:none}
#play[data-state=playing] .when-paused,#play[data-state=paused] .when-playing{display:none}
#panel-count{min-width:1.5em;text-align:center;font-variant-numeric:tabular-nums;font-weight:500;color:#fff}
#families{display:flex}
#families button[aria-checked=true]{background:rgba(255,255,255,.17);color:#fff}
#families button[aria-checked=false]{color:var(--dim)}
#effects[aria-pressed=true]{background:rgba(255,255,255,.17);color:#fff}
.lab-link{color:var(--fg);text-decoration:none;font-size:12px;padding:10px 12px;border-radius:999px;white-space:nowrap}
.lab-link:hover{background:rgba(255,255,255,.1);color:#fff}
#sound{display:flex;align-items:center}
#volume{width:0;opacity:0;margin:0;height:44px;accent-color:#fff;cursor:pointer;
transition:width 200ms var(--ease),opacity 200ms var(--ease),margin 200ms var(--ease)}
#sound:hover #volume,#sound:focus-within #volume{width:84px;opacity:1;margin:0 8px 0 2px}
[data-sound=on] .s-off,[data-sound=on] .s-lock,[data-sound=off] .s-on,[data-sound=off] .s-lock,
[data-sound=locked] .s-on,[data-sound=locked] .s-off{display:none}
[data-sound=locked] #speaker::after{content:"";position:absolute;inset:6px;border-radius:999px;
border:1.5px solid rgba(255,255,255,.7);animation:pulse 2.4s var(--ease) infinite}
@keyframes pulse{0%{transform:scale(.8);opacity:.9}70%,100%{transform:scale(1.35);opacity:0}}
#help{font-weight:600;font-size:17px}
#start{position:fixed;left:50%;top:50%;width:88px;height:88px;transform:translate(-50%,-50%);display:none;
background:var(--glass);border:1px solid var(--edge);-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}
#start svg{width:34px;height:34px}
.held #start{display:inline-flex}
#toast{position:fixed;left:50%;bottom:calc(84px + env(safe-area-inset-bottom));transform:translate(-50%,6px);
max-width:min(92vw,32rem);padding:10px 16px;border-radius:14px;background:var(--glass);border:1px solid var(--edge);
-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);text-align:center;font-size:14px;opacity:0;
pointer-events:none;transition:opacity 200ms var(--ease),transform 200ms var(--ease)}
#toast.on{opacity:1;transform:translate(-50%,0)}
#about{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:min(88vw,22rem);margin:0;
padding:18px 20px;border-radius:18px;background:rgba(16,16,18,.72);border:1px solid var(--edge);
-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);box-shadow:0 20px 60px rgba(0,0,0,.5)}
#about p{margin:0 0 8px}#about p:last-child{margin:0;color:var(--dim);font-size:13px}
#about:focus-visible{outline-offset:-2px}
#filter-settings{color:var(--fg);background:rgba(16,16,18,.97);border:1px solid var(--edge);
border-radius:18px;padding:18px;width:min(92vw,24rem);max-height:82vh;overflow:auto;
box-shadow:0 20px 60px rgba(0,0,0,.5)}
#filter-settings::backdrop{background:rgba(0,0,0,.35)}
#filter-settings header{display:flex;align-items:center;justify-content:space-between;gap:8px}
#filter-settings h2{font-size:18px;margin:0}#filter-settings p{font-size:13px;color:var(--dim);margin:4px 0 14px}
#filter-settings fieldset{border:0;border-top:1px solid var(--edge);margin:10px 0;padding:10px 0 0}
#filter-settings legend{font-weight:600;padding:0 6px 0 0}
.filter-control{display:grid;grid-template-columns:1fr auto;gap:4px 12px;margin:8px 0}
.filter-control output{font-variant-numeric:tabular-nums;color:var(--dim)}
.filter-control input{grid-column:1/-1;width:100%;min-height:32px;margin:0;accent-color:#fff}
#fx-curve{background:#222;color:var(--fg);border:1px solid var(--edge);border-radius:8px;
font:inherit;padding:7px;width:100%;margin-top:4px}
#fx-reset{width:auto;padding:0 14px;border:1px solid var(--edge)}
#drop{position:fixed;inset:12px;border:1.5px dashed rgba(255,255,255,.6);border-radius:22px;display:none;
align-items:center;justify-content:center;background:rgba(0,0,0,.35);pointer-events:none}
#drop svg{width:56px;height:56px;fill:none;stroke:#fff;stroke-width:1.2;stroke-linecap:round}
.dragging #drop{display:flex}
@media (max-width:480px){button{width:40px;height:40px}#bar{padding:4px;gap:0}.sep{margin:0 2px}
#families button[aria-checked=false]{display:none}#sound:hover #volume{width:0;opacity:0;margin:0}
#sound:focus-within #volume{width:72px;opacity:1;margin:0 6px 0 0}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important}}
'''
STYLE_HASH = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
# Same-origin scripts, layouts.json and the optional library/ only; every loop plays from a blob: URL
# made on this device.
CONTENT_SECURITY_POLICY = ("default-src 'none'; script-src 'self'; connect-src 'self'; media-src blob:; "
                           f"img-src blob:; style-src 'sha256-{STYLE_HASH}'; base-uri 'none'; form-action 'none'")


def _icon(body: str) -> str:
    return f'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{body}</svg>'


PLAY_ICON = ('<path class="fill when-paused" d="M8 5.5v13l10.5-6.5z"/>'
             '<rect class="fill when-playing" x="7" y="5.5" width="3.6" height="13" rx="1"/>'
             '<rect class="fill when-playing" x="13.4" y="5.5" width="3.6" height="13" rx="1"/>')
ICONS = {
    'play': _icon(PLAY_ICON),
    'start': _icon('<path class="fill" d="M8 5.5v13l10.5-6.5z"/>'),
    'shuffle': _icon('<path d="M3 7h3.2c2.4 0 3.7 1.2 5 3.5l1.6 3c1.3 2.3 2.6 3.5 5 3.5H21"/>'
                     '<path d="M3 17h3.2c1.5 0 2.6-.5 3.5-1.4M14.3 8.4c.9-.9 2-1.4 3.5-1.4H21"/>'
                     '<path d="M18 4l3 3-3 3M18 14l3 3-3 3"/>'),
    'fewer': _icon('<path d="M6 12h12"/>'),
    'more': _icon('<path d="M12 6v12M6 12h12"/>'),
    'speaker': _icon('<path d="M4 9.5h3l5-4v13l-5-4H4z"/>'
                     '<path class="s-on" d="M15.5 9a4.2 4.2 0 0 1 0 6M18 6.5a7.8 7.8 0 0 1 0 11"/>'
                     '<path class="s-off" d="M16 9.5l5 5M21 9.5l-5 5"/>'
                     '<path class="s-lock" d="M16.5 12h.01M19.5 12h.01"/>'),
    'add': _icon('<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5l5-3v9l-5-3"/>'
                 '<path d="M9.5 9.5v5M7 12h5"/>'),
    'fullscreen': _icon('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
    'drop': _icon('<path d="M12 5v14M5 12h14"/>'),
}

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="''' + CONTENT_SECURITY_POLICY + '''">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#0a0a0b">
<meta name="description" content="Loops on their own clocks, colliding by accident. Add your own videos; they never leave this device.">
<title>''' + STUDIO_TITLE + '''</title>
<style>''' + STYLE + '''</style>
</head>
<body>
<main id="studio">
<h1 class="visually-hidden">SIMVLTANEA studio</h1>
<div id="frame">
<div id="stage" role="region" aria-label="Loops playing at once"></div>
<div id="preview" aria-hidden="true"></div>
<div id="ghost" aria-hidden="true"></div>
</div>
<button id="start" type="button" aria-label="Play">''' + ICONS['start'] + '''</button>
<div id="bar" role="toolbar" aria-label="Controls">
<button id="play" type="button" aria-label="Pause" data-state="playing">''' + ICONS['play'] + '''</button>
<button id="shuffle" type="button" aria-label="Shuffle" aria-keyshortcuts="R">''' + ICONS['shuffle'] + '''</button>
<span class="sep" aria-hidden="true"></span>
<div role="group" aria-label="Panels">
<button id="fewer" type="button" aria-label="Fewer panels">''' + ICONS['fewer'] + '''</button>
<output id="panel-count" aria-live="polite"></output>
<button id="more" type="button" aria-label="More panels">''' + ICONS['more'] + '''</button>
</div>
<span class="sep" aria-hidden="true"></span>
<div id="families" role="radiogroup" aria-label="Layout"></div>
<span class="sep" aria-hidden="true"></span>
<div id="sound">
<button id="speaker" type="button" aria-label="Tap for sound" aria-keyshortcuts="M">''' + ICONS['speaker'] + '''</button>
<input id="volume" type="range" min="0" max="100" step="1" value="70" aria-label="Volume">
</div>
<button id="add" type="button" aria-label="Add your own videos">''' + ICONS['add'] + '''</button>
<input id="files" class="visually-hidden" type="file" multiple tabindex="-1" aria-hidden="true"
accept="video/*,.mov,.mp4,.m4v,.webm,.json,application/json">
</div>
<div id="corner" role="toolbar" aria-label="Page">
<a class="lab-link" href="lab.html">Effects Lab</a>
<button id="activity" type="button" aria-label="Hold changes" aria-pressed="false" title="Hold changes">∞</button>
<button id="effects" type="button" aria-label="Filters" aria-pressed="true" title="Filters on">ƒx</button>
<button id="filter-tune" type="button" aria-label="Filter settings" aria-haspopup="dialog"
aria-controls="filter-settings" aria-expanded="false" title="Filter settings">☷</button>
<button id="loop-mode" type="button" aria-label="Play forward loops" title="Boomerang loops" hidden>↔</button>
<button id="fullscreen" type="button" aria-label="Full screen" aria-keyshortcuts="F">''' + ICONS['fullscreen'] + '''</button>
<button id="help" type="button" aria-label="About this page" aria-expanded="false" aria-controls="about">?</button>
</div>
<dialog id="filter-settings" aria-labelledby="filter-title">
<header><h2 id="filter-title">Clip filters</h2><button id="fx-close" type="button" aria-label="Close filter settings">×</button></header>
<p>Each clip rises and recedes on its own. Set any effect to zero to bypass it.</p>
<fieldset><legend>Timing</legend>
<div class="filter-control"><label for="fx-attack">Rise</label><output id="fx-attack-value" for="fx-attack">1.2 s</output>
<input id="fx-attack" type="range" min="0.1" max="5" step="0.1" value="1.2"></div>
<label for="fx-curve">Curve</label><select id="fx-curve"><option value="linear">Linear</option><option value="smooth">Smooth</option></select>
<div class="filter-control"><label for="fx-tail">Waiting presence</label><output id="fx-tail-value" for="fx-tail">12%</output>
<input id="fx-tail" type="range" min="5" max="50" step="1" value="12"></div>
</fieldset>
<fieldset><legend>Sound</legend>
<div class="filter-control"><label for="fx-gain">Volume swell</label><output id="fx-gain-value" for="fx-gain">100%</output>
<input id="fx-gain" type="range" min="0" max="100" step="1" value="100"></div>
<div class="filter-control"><label for="fx-lowpass">Low-pass filter</label><output id="fx-lowpass-value" for="fx-lowpass">100%</output>
<input id="fx-lowpass" type="range" min="0" max="100" step="1" value="100"></div>
</fieldset>
<fieldset><legend>Image</legend>
<div class="filter-control"><label for="fx-brightness">Brightness swell</label><output id="fx-brightness-value" for="fx-brightness">100%</output>
<input id="fx-brightness" type="range" min="0" max="100" step="1" value="100"></div>
<div class="filter-control"><label for="fx-saturation">Color swell</label><output id="fx-saturation-value" for="fx-saturation">100%</output>
<input id="fx-saturation" type="range" min="0" max="100" step="1" value="100"></div>
<div class="filter-control"><label for="fx-blur">Blur</label><output id="fx-blur-value" for="fx-blur">2 px</output>
<input id="fx-blur" type="range" min="0" max="2" step="0.1" value="2"></div>
</fieldset>
<button id="fx-reset" type="button">Reset filters</button>
</dialog>
<div id="about" role="dialog" aria-label="About" tabindex="-1" hidden>
<p>Loops on their own clocks, rising and receding in sound and image. ƒx toggles filters; ☷ adjusts them; ∞ holds changes; ↔ switches loop direction.</p>
<p>Your videos never leave this device. Nothing is uploaded.</p>
<p>Space play · R shuffle · M sound · F full screen · ← → panels</p>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<p id="runtime-note" hidden></p>
<div id="drop" aria-hidden="true">''' + ICONS['drop'] + '''</div>
</main>
<script src="compiler.js" defer></script>
<script src="runtime.js" defer></script>
<script src="studio.js" defer></script>
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
        'runtime.js': b'\n'.join((HERE / name).read_bytes() for name in
                                ('browser.audio.js', 'browser.presence.js', 'browser.ecosystem.js', 'browser.live.js')),
        'compiler.js': (HERE / 'browser.compiler.js').read_bytes(),
        'studio.js': (HERE / 'browser.studio.js').read_bytes(),
        'layouts.json': layouts.encode(),
        **lab_files(),
    }


def stage_studio(output: Path) -> None:
    """Write the flat studio into ``output``, creating it when absent.

    Only the declared Studio and Effects Lab files are ever written. A directory holding anything
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
