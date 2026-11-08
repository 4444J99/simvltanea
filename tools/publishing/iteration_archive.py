"""Build preserved historical interfaces from verified source snapshots.

Only the resulting browser assets enter the public site. Archived Python source,
provenance records and the build machine's paths never enter the release.
"""
from __future__ import annotations
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from simvltanea.paths import REPO_ROOT
from simvltanea.browser import ARCHIVED_ITERATIONS

ARCHIVE_ROOT = REPO_ROOT / "archive" / "engineered-iterations"

def verify_source_archive(directory: Path) -> dict:
    directory = Path(directory)
    if directory.is_symlink() or (directory / "manifest.json").is_symlink():
        raise ValueError("source archive must not be linked")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "simvltanea.engineered-source/1":
        raise ValueError("unsupported source archive schema")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", "")):
        raise ValueError("source archive needs a full revision")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("empty source archive")
    seen = set()
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in seen:
            raise ValueError("unsafe or duplicate source path")
        seen.add(relative.as_posix())
        source = directory / "source" / relative
        if any(part.is_symlink() for part in (source, *source.parents)) or not source.is_file():
            raise ValueError("source archive contains a missing or linked file")
        body = source.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
        if hashlib.sha256(body).hexdigest() != record["sha256"] or blob != record["git_blob"]:
            raise ValueError("source archive digest mismatch")
    actual = set()
    for source in (directory / "source").rglob("*"):
        if source.is_symlink():
            raise ValueError("source archive contains a linked file")
        if source.is_file():
            actual.add(source.relative_to(directory / "source").as_posix())
    if actual != seen:
        raise ValueError("source archive contains unlisted files")
    return manifest

def _studio_files(item: dict, directory: Path) -> dict[str, bytes]:
    env = dict(os.environ, PYTHONPATH=str(directory / "source" / "src"),
               PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="iteration-studio-") as temporary:
        output = Path(temporary) / "site"
        result = subprocess.run(
            [sys.executable, "-m", "simvltanea.browser.browser_studio", "--output", str(output)],
            cwd=directory / "source", env=env, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise ValueError("historical Studio staging failed for " + item["slug"] + ": " + result.stderr[-1800:])
        files = {}
        for source in output.iterdir():
            if source.is_symlink() or not source.is_file() or source.suffix not in (".html", ".js", ".json"):
                raise ValueError("historical Studio emitted an unexpected asset")
            files[source.name] = source.read_bytes()
        if not {"index.html", "studio.js", "runtime.js", "compiler.js", "layouts.json"} <= files.keys():
            raise ValueError("historical Studio is incomplete")
        # The published-library interface expects its library beside its own HTML.
        # This small loading adapter maps that request to the shared, admitted library.
        if item["slug"] == "studio-library":
            files["replay-library.js"] = LIBRARY_ADAPTER.encode()
            files["index.html"] = files["index.html"].replace(
                b"<head>", b'<head><script src="replay-library.js"></script>', 1)
        return files

LIBRARY_ADAPTER = """'use strict';
{
 const nativeFetch = window.fetch.bind(window);
 window.fetch = function(input, init) {
  if(typeof input === 'string' && input.startsWith('library/'))
   input = '../../../' + input;
  return nativeFetch(input, init);
 };
}
"""

def _lab_files(directory: Path, clips: list[dict]) -> dict[str, bytes]:
    app = directory / "source/src/simvltanea/lab/app"
    files = {path.name: path.read_bytes() for path in app.iterdir()
             if path.is_file() and path.suffix in (".html", ".css", ".js")}
    records = []
    for clip in clips:
        records.append(dict(
            id=clip["id"], video="../../../library/"+clip["file"], still="",
            duration=clip["duration_seconds"], width=clip["width"], height=clip["height"],
            orientation=clip["orientation"], has_audio=clip.get("has_audio", False),
            loudness_db=clip.get("lufs_integrated"), audio={"screened": False},
            captured_at=None, tags=clip.get("tags", {}), features={}))
    files["data/clips.json"] = json.dumps({"version": 1, "clips": records}, separators=(",", ":")).encode()
    return files

WRAPPER_CSS = """
*{box-sizing:border-box}html,body{height:100%;margin:0;background:#111317;color:#eee;font:14px system-ui}
body{display:flex;flex-direction:column}header{padding:10px 16px;background:#1c2025;border-bottom:1px solid #3b4047}
.title{display:flex;gap:14px;align-items:center;flex-wrap:wrap}h1{font-size:16px;margin:0;flex:1}
a{color:#c5eccf}a:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid #b3e2be;outline-offset:3px}
small{color:#b8bec8}button{background:#c5eccf;color:#15251b;border:0;border-radius:5px;padding:9px 12px;font:inherit;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}details{margin-top:8px;color:#b8bec8;font-size:12px}summary{cursor:pointer}
details p{max-width:76ch;line-height:1.5;margin:8px 0}iframe{border:0;width:100%;flex:1;min-height:0;background:#08090b}
#status{margin:0;padding:5px 16px;color:#c5eccf;background:#1c2025;font-size:12px}
@media(max-width:540px){header{padding:9px 10px}.title{gap:8px}h1{font-size:13px;min-width:50%}a,button{font-size:12px}}
"""

WRAPPER_JS = """'use strict';
const frame=document.getElementById('original');
const load=document.getElementById('load-examples');
const status=document.getElementById('status');
const kind=document.body.dataset.kind;
let busy=false, token=0, playbackObserver;
const pauseOriginal=()=>{
 const w=frame.contentWindow;
 try{
  if(w.__lab?.player && !w.__lab.paused()) w.__lab.player.togglePause();
  const control=w.document.getElementById('play') || w.document.getElementById('toggle');
  if(control && /pause/i.test(control.getAttribute('aria-label') || control.textContent)) control.click();
  const r=w.compositionRuntime;
  if(r?.running && typeof r.pause==='function') r.pause();
 }catch{}
};
document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseOriginal();});
async function waitFor(read, seconds=35){
 const start=performance.now();
 while(performance.now()-start<seconds*1000){
  const result=read();if(result)return result;
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('The original interface has not finished preparing the clips.');
}
async function examples(){
 if(busy)return;busy=true;load.disabled=true;
 const current=++token;
 status.textContent='Loading clips from the current public library…';
 try{
  const manifest=await fetch('../../library/manifest.json').then(r=>{if(!r.ok)throw Error('The public library is unavailable.');return r.json();});
  const chosen=manifest.clips.filter(c=>c.duration_seconds>=1&&c.duration_seconds<=15).slice(0,3);
  if(chosen.length<2)throw Error('At least two distinct public clips are required.');
  const doc=frame.contentDocument;
  const input=await waitFor(()=>doc.getElementById('files'));
  await waitFor(()=>frame.contentWindow.SimvltaneaStudio?.snapshot && !frame.contentWindow.SimvltaneaStudio.snapshot().loading);
  const transfer=new frame.contentWindow.DataTransfer();
  for(const clip of chosen){
   const response=await fetch('../../library/'+clip.file);
   if(!response.ok)throw Error('A public clip could not be loaded.');
   const blob=await response.blob();
   transfer.items.add(new frame.contentWindow.File([blob],clip.id+'.mp4',{type:'video/mp4'}));
  }
  if(current!==token)return;
  input.files=transfer.files;input.dispatchEvent(new frame.contentWindow.Event('change',{bubbles:true}));
  await waitFor(()=>{
   const state=frame.contentWindow.SimvltaneaStudio.snapshot();
   return !state.busy && state.loops.length>=chosen.length;
  });
  frame.style.visibility='visible';
  if(document.hidden)pauseOriginal();
  status.textContent='Public clips loaded. Use the original controls below.';
 }catch(error){
  frame.style.visibility='visible';
  status.textContent=error.message+' You can also import your own video files below.';
 }finally{busy=false;load.disabled=false;}
}
frame.addEventListener('load',()=>{
 playbackObserver?.disconnect();
 playbackObserver=new MutationObserver(()=>{if(document.hidden)pauseOriginal();});
 playbackObserver.observe(frame.contentDocument.body,{subtree:true,attributes:true,
  attributeFilter:['aria-label','data-status','data-state']});
 if(document.hidden)pauseOriginal();
 if(kind==='lab'){
  status.textContent='Original Lab loaded with public clips. Its original audio screening defaults are preserved.';
 }else if(document.body.dataset.slug==='studio-library'){
  frame.style.visibility='visible';
  status.textContent='Original public-library Studio. Clips come from the current public library.';
  load.disabled=false;
 }else{
  frame.style.visibility='hidden';
  load.disabled=false;examples();
 }
});
load?.addEventListener('click',examples);
"""

def _wrapper(item: dict) -> bytes:
    title = html.escape(item["title"])
    description = html.escape(item["description"])
    date = html.escape(item["date"])
    note = ("The original audio-screening defaults are retained; imported public clips have no Lab speech-screen record. "
            "The Audio module lets you control which sources sound." if item["kind"] == "lab" else
            "Use the original controls to start, stop or change the arrangement. You can import your own files.")
    button = ('<button id="load-examples" disabled>Load public clips</button>' if item["kind"] == "studio"
              else '<button id="load-examples" hidden>Load public clips</button>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{title} · SIMVLTANEA iterations</title><link rel="stylesheet" href="../replay.css">'
        '<script src="../archive.js" defer></script></head>'
        f'<body data-kind="{item["kind"]}" data-slug="{item["slug"]}"><header><div class="title">'
        f'<a href="../../iterations.html">← All iterations</a><h1>{title}</h1><small>{date}</small>{button}</div>'
        f'<details><summary>About this version</summary><p>{description}</p>'
        '<p>This preserved interface uses the current public clip library. It does not recreate an original historical arrangement or its private media.</p>'
        f'<p>{note}</p><p>Source revision: <code>{item["revision"]}</code>.</p></details></header>'
        '<p id="status" role="status">Loading the preserved interface…</p>'
        '<iframe id="original" src="original/index.html" title="Preserved original interface" allow="autoplay; fullscreen"></iframe>'
        '</body></html>').encode()

def preserved_iteration_files(clips: list[dict]) -> dict[str, bytes]:
    result = {"iterations/replay.css": WRAPPER_CSS.encode(),
              "iterations/archive.js": WRAPPER_JS.encode()}
    for item in ARCHIVED_ITERATIONS:
        directory = ARCHIVE_ROOT / item["slug"]
        manifest = verify_source_archive(directory)
        if (manifest["revision"] != item["revision"] or manifest["kind"] != item["kind"]
                or manifest["slug"] != item["slug"]):
            raise ValueError("source archive identity differs from the iteration catalog")
        original = _studio_files(item, directory) if item["kind"] == "studio" else _lab_files(directory, clips)
        base = "iterations/" + item["slug"] + "/"
        result[base + "index.html"] = _wrapper(item)
        for name, body in original.items():
            result[base + "original/" + name] = body
    return result
