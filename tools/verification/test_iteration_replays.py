"""Focused contract checks for the four preserved early renderer replays."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import shutil
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from tools.publishing.iteration_replays import (
    ARCHIVE_ROOT, HISTORICAL_REPLAYS, REPLAY_JS, historical_replay_files,
)


CLIPS = [
    {"id": "alpha", "file": "alpha.mp4", "width": 1280, "height": 720,
     "duration_seconds": 8.125, "bytes": 1234, "has_audio": True},
    {"id": "beta", "file": "beta.mp4", "width": 720, "height": 1280,
     "duration_seconds": 11.5, "bytes": 2345, "has_audio": False},
    {"id": "gamma", "file": "gamma.mp4", "width": 1920, "height": 1080,
     "duration_seconds": 4.25, "bytes": 3456, "has_audio": True},
]


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("src", "href"):
                self.references.append(value)


class HistoricalReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = historical_replay_files(CLIPS)

    def plan(self, slug, audio=False):
        return json.loads(self.files[f"iterations/{slug}/{'audio-plan' if audio else 'plan'}.json"])

    def test_all_four_routes_and_exact_pinned_runtime_bytes(self):
        provenance = json.loads((ARCHIVE_ROOT / "source-provenance.json").read_text())
        records = {record["slug"]: record for record in provenance["sources"]}
        self.assertEqual(len(HISTORICAL_REPLAYS), 4)
        for item in HISTORICAL_REPLAYS:
            with self.subTest(slug=item["slug"]):
                root = "iterations/" + item["slug"] + "/"
                self.assertTrue({root + name for name in ("index.html", "replay.js", "replay.css", "runtime.js", "plan.json", "provenance.json")} <= self.files.keys())
                archived = (ARCHIVE_ROOT / item["slug"] / "browser_runtime.js").read_bytes()
                self.assertEqual(self.files[root + "runtime.js"], archived)
                self.assertEqual(hashlib.sha256(archived).hexdigest(), item["source_sha256"])
                self.assertEqual(records[item["slug"]]["sha256"], item["source_sha256"])
                self.assertEqual(records[item["slug"]]["bytes"], len(archived))
                self.assertEqual(records[item["slug"]]["revision"], item["revision"])
                self.assertEqual(records[item["slug"]]["source_path"], item["source_path"])
                self.assertRegex(item["revision"], r"^[0-9a-f]{40}$")
                utc_date = datetime.fromisoformat(records[item["slug"]]["committed_at"]).astimezone(timezone.utc).date().isoformat()
                self.assertEqual(item["date"], utc_date)

    def test_real_public_paths_no_copied_or_invented_media(self):
        for item in HISTORICAL_REPLAYS:
            plan = self.plan(item["slug"])
            self.assertEqual({source["path"] for source in plan["sources"]}, {"../../library/" + clip["file"] for clip in CLIPS})
            self.assertEqual(len({source["id"] for source in plan["sources"]}), 3)
            self.assertEqual(len({track["spans"][0]["source"] for track in plan["tracks"]}), 3)
        self.assertFalse(any(Path(path).suffix in (".mp4", ".mp3", ".wav", ".webm") for path in self.files))
        self.assertIn("window.compositionIO", REPLAY_JS)
        self.assertIn("bytes.byteLength !== source.bytes", REPLAY_JS)
        self.assertIn("source.sha256 = hash", REPLAY_JS)
        self.assertNotIn("createOscillator", REPLAY_JS)

    def test_selection_is_deterministic_distinct_and_does_not_mutate_input(self):
        before = json.dumps(CLIPS, sort_keys=True)
        repeated = [*CLIPS, dict(CLIPS[0]), {**CLIPS[1], "id": "different-id"}]
        self.assertEqual(historical_replay_files(list(reversed(repeated))), self.files)
        self.assertEqual(json.dumps(CLIPS, sort_keys=True), before)
        one = historical_replay_files([CLIPS[0]])
        for item in HISTORICAL_REPLAYS:
            self.assertEqual(len(json.loads(one[f"iterations/{item['slug']}/plan.json"])["tracks"]), 1)

    def test_independent_rates_and_bounded_source_spans(self):
        for item in HISTORICAL_REPLAYS:
            plan = self.plan(item["slug"])
            sources = {source["id"]: source for source in plan["sources"]}
            rates = set()
            for track in plan["tracks"]:
                spans = track["spans"]
                for index, span in enumerate(spans):
                    next_frame = spans[index + 1]["frame"] if index + 1 < len(spans) else plan["frames"]
                    duration = Fraction(sources[span["source"]]["duration"])
                    rate, offset = Fraction(span["rate"]), Fraction(span["source_offset"])
                    self.assertGreaterEqual(rate, Fraction(1, 16))
                    self.assertLessEqual(rate, 8)
                    self.assertLessEqual(offset + Fraction(next_frame - span["frame"], plan["fps"]) * rate, duration)
                    self.assertFalse(span["held"])
                    rates.add(rate)
            self.assertEqual(rates, {Fraction(1), Fraction(7, 8), Fraction(5, 4)})

    def test_silent_schema_one_and_explicit_audio_schema_two(self):
        for item in HISTORICAL_REPLAYS:
            plan = self.plan(item["slug"])
            self.assertEqual((plan["plan_version"], plan["engine_version"], plan["audio"]), (1, "1.0.0", "none"))
            audio_path = f"iterations/{item['slug']}/audio-plan.json"
            supported = item["slug"] in ("spatial-audio", "viewport-composition")
            self.assertEqual(audio_path in self.files, supported)
            if supported:
                audio = self.plan(item["slug"], audio=True)
                self.assertEqual((audio["plan_version"], audio["engine_version"], audio["audio"]["mode"]), (2, "1.1.0", "spatial_loops"))
                self.assertEqual(set(audio["audio"]["per_loop"]), {track["id"] for track in audio["tracks"]})
                self.assertTrue(all(source["audio_stream"] is None for source in audio["sources"]))
                self.assertTrue(all(settings["mute_on_hold"] for settings in audio["audio"]["per_loop"].values()))
                self.assertIn(b'href="?audio=1"', self.files[f"iterations/{item['slug']}/index.html"])
        silent = historical_replay_files([{**clip, "has_audio": False} for clip in CLIPS])
        self.assertFalse(any(path.endswith("audio-plan.json") for path in silent))
        self.assertNotIn(".start();", REPLAY_JS.split("play.addEventListener", 1)[0])

    def test_crop_features_and_paired_orientation_layouts(self):
        for item in HISTORICAL_REPLAYS:
            plan = self.plan(item["slug"])
            for track in plan["tracks"]:
                self.assertEqual("slice_rect" in track["spans"][0], item["slug"] != "authored-loops")
            layouts = plan["layout_keyframes"][0]["layouts"]
            self.assertEqual(set(layouts), {"portrait", "landscape"})
            for layout in layouts.values():
                self.assertEqual({cell["loop"] for cell in layout["cells"]}, {track["id"] for track in plan["tracks"]})
                self.assertTrue(all(cell["fit"] == "cover" for cell in layout["cells"]))

    def test_all_html_asset_references_resolve(self):
        for item in HISTORICAL_REPLAYS:
            prefix = "iterations/" + item["slug"] + "/"
            parser = References()
            parser.feed(self.files[prefix + "index.html"].decode())
            for ref in parser.references:
                parsed = urlsplit(ref)
                self.assertFalse(parsed.scheme or parsed.netloc)
                if not parsed.path or parsed.path in ("./", "../"):
                    continue
                target = posixpath.normpath(posixpath.join(prefix, parsed.path))
                if target == "iterations.html":
                    self.assertEqual(ref, "../../iterations.html")
                elif target.startswith("library/"):
                    self.assertIn(unquote(target.removeprefix("library/")), {clip["file"] for clip in CLIPS})
                else:
                    self.assertIn(target, self.files)

    def test_escaping_and_same_origin_paths(self):
        clip = {**CLIPS[0], "id": '<script>alert("x")</script>', "file": 'a & "quoted" clip.mp4'}
        files = historical_replay_files([clip])
        page = files["iterations/authored-loops/index.html"].decode()
        self.assertNotIn(clip["id"], page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("a%20%26%20%22quoted%22%20clip.mp4", page)
        plan = json.loads(files["iterations/authored-loops/plan.json"])
        self.assertEqual(plan["sources"][0]["id"], "source-1")
        self.assertEqual(plan["sources"][0]["path"], "../../library/a%20%26%20%22quoted%22%20clip.mp4")
        for unsafe in ("../escape.mp4", "/escape.mp4", "https://example.com/x.mp4", "a\\b.mp4", "a.mp4?secret", "a.mp4#x"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                historical_replay_files([{**CLIPS[0], "file": unsafe}])

    def test_clear_empty_or_oversized_library_failure(self):
        for clips in ([], [{**CLIPS[0], "bytes": 257 * 1024 * 1024}]):
            with self.assertRaisesRegex(ValueError, "at least one playable public clip"):
                historical_replay_files(clips)

    def test_source_tampering_is_rejected(self):
        real_read = Path.read_bytes
        def changed(path):
            data = real_read(path)
            return data + b"\n" if path.name == "browser_runtime.js" else data
        with patch.object(Path, "read_bytes", changed), self.assertRaisesRegex(ValueError, "digest mismatch"):
            historical_replay_files(CLIPS)

    def test_unavailable_external_framing_is_disclosed(self):
        page = self.files["iterations/viewport-composition/index.html"].decode()
        self.assertIn("external shared-engine framing package is not included", page)
        self.assertIn("preserved native compositor", page)
        self.assertIn("!engine.ready || Boolean(engine.error)", REPLAY_JS)
        self.assertNotIn("host.dataset.status === 'error'", REPLAY_JS)
        for item in HISTORICAL_REPLAYS:
            page = self.files[f"iterations/{item['slug']}/index.html"].decode()
            self.assertIn("not a recovered original artwork state", page)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable for replay adapter checks")
    def test_actual_loading_adapter_rejects_same_size_corruption(self):
        original = b"public-media-fixture"
        content_id = hashlib.sha256(original).hexdigest()[:12]
        clips = [{**CLIPS[0], "id": content_id, "file": "clips/" + content_id + ".mp4", "bytes": len(original)}]
        files = historical_replay_files(clips)
        plan = json.loads(files["iterations/authored-loops/plan.json"])
        harness = r'''const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
async function load(corrupt){
 const fixture=Buffer.from(input.bytes);if(corrupt)fixture[0]^=1;
 const element=()=>({addEventListener(){},classList:{toggle(){return false;}}});
 const nodes=new Map();const window={addEventListener(){}};
 const context={window,URL,URLSearchParams,Map,Array,Uint8Array,Error,
 crypto:require('crypto').webcrypto,setInterval(){},
 document:{addEventListener(){},body:{dataset:{audioPlan:'false',iteration:'authored-loops'}},
  querySelector(key){if(!nodes.has(key))nodes.set(key,element());return nodes.get(key);}},
 location:{href:'https://example.test/iterations/authored-loops/',origin:'https://example.test',search:''},
 async fetch(url){if(url==='plan.json')return{ok:true,json:async()=>JSON.parse(JSON.stringify(input.plan))};
  assert.equal(String(url),'https://example.test/library/clips/'+input.id+'.mp4');
  return{ok:true,arrayBuffer:async()=>fixture.buffer.slice(fixture.byteOffset,fixture.byteOffset+fixture.byteLength)};}
 };
 vm.runInNewContext(input.script,context);
 return window.compositionIO.plan();
}
(async()=>{const plan=await load(false);
 assert.equal(plan.sources[0].sha256,input.hash);assert.equal(plan.sources[0].public_id,undefined);
 await assert.rejects(()=>load(true),/Public media integrity differs/);
})().catch(error=>{console.error(error);process.exitCode=1;});'''
        payload = {"script": REPLAY_JS, "plan": plan, "bytes": list(original),
                   "id": content_id, "hash": hashlib.sha256(original).hexdigest()}
        result = subprocess.run(["node", "-e", harness], input=json.dumps(payload), text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable for historical JavaScript validator checks")
    def test_real_historical_validators_accept_adapter_normalized_plans(self):
        # Exercise the archived validator itself.  The same public-path to
        # content-addressed-envelope normalization is performed by compositionIO
        # in the browser; fixture bytes are not claimed to be playable media.
        harness = r'''const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));
for(const entry of input){
 const source=entry.source;
 const number=source.slice(source.indexOf('const number ='),source.indexOf('const stage ='));
 const validation=source.slice(source.indexOf('function validatePlan(plan)'),source.indexOf('async function initialize()'));
 const validate=new Function(number+'\n'+validation+'\nreturn validatePlan;')();
 for(const plan of entry.plans){
  for(const source of plan.sources){source.sha256='a'.repeat(64);source.path='media/'+source.sha256+'.mp4';}
  validate(plan);
 }
}'''
        entries = []
        for item in HISTORICAL_REPLAYS:
            plans = [self.plan(item["slug"])]
            if f"iterations/{item['slug']}/audio-plan.json" in self.files:
                plans.append(self.plan(item["slug"], audio=True))
            entries.append({"source": self.files[f"iterations/{item['slug']}/runtime.js"].decode(), "plans": plans})
        result = subprocess.run(["node", "-e", harness], input=json.dumps(entries), text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        syntax = subprocess.run(["node", "--check"], input=REPLAY_JS, text=True, capture_output=True, timeout=10)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
