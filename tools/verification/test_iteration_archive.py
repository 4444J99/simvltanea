"""Preserved interfaces must be playable releases with source identity and shared public media."""
from pathlib import Path
import json
import tempfile
import unittest
from tools.publishing.iteration_archive import preserved_iteration_files, verify_source_archive, ARCHIVE_ROOT
from simvltanea.browser import ARCHIVED_ITERATIONS, ENGINEERED_ITERATIONS

def clips():
    return [dict(id=f"{i:012x}",file=f"clips/{i:012x}.mp4",width=640,height=360,
                 orientation="landscape",duration_seconds=4,bytes=100,
                 has_audio=True,lufs_integrated=-24,peak_dbfs=-6,
                 envelope_hz=10,rms_envelope=[.1]*40,tags={}) for i in range(1,8)]

class PreservedIterationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = preserved_iteration_files(clips())

    def test_every_archived_interface_has_a_working_entry_and_its_original_page(self):
        for item in ARCHIVED_ITERATIONS:
            base="iterations/"+item["slug"]+"/"
            with self.subTest(slug=item["slug"]):
                self.assertIn(base+"index.html",self.files)
                self.assertIn(base+"original/index.html",self.files)
                self.assertIn('src="original/index.html"',self.files[base+"index.html"].decode())
                self.assertIn("current public clip library",self.files[base+"index.html"].decode())

    def test_lab_media_points_to_existing_shared_library_without_inventing_screening(self):
        for item in ARCHIVED_ITERATIONS:
            if item["kind"]!="lab": continue
            payload=json.loads(self.files[f'iterations/{item["slug"]}/original/data/clips.json'])
            self.assertEqual(len(payload["clips"]),7)
            for record,source in zip(payload["clips"],clips()):
                self.assertEqual(record["video"],"../../../library/"+source["file"])
                self.assertEqual(record["has_audio"],source["has_audio"])
                self.assertFalse(record["audio"]["screened"])
                self.assertEqual(record["still"],"")

    def test_original_lab_sources_are_unmodified(self):
        for item in ARCHIVED_ITERATIONS:
            if item["kind"]!="lab": continue
            for name in ("index.html","main.js","player.js","params.js"):
                source=ARCHIVE_ROOT/item["slug"]/"source/src/simvltanea/lab/app"/name
                self.assertEqual(self.files[f'iterations/{item["slug"]}/original/{name}'],source.read_bytes())

    def test_source_archives_have_full_revision_pins_and_valid_digests(self):
        for item in ARCHIVED_ITERATIONS:
            manifest=verify_source_archive(ARCHIVE_ROOT/item["slug"])
            self.assertEqual(manifest["revision"],item["revision"])
            self.assertRegex(manifest["revision"],r"^[0-9a-f]{40}$")
            self.assertTrue(manifest["files"])

    def test_source_code_and_private_paths_are_not_published(self):
        for path,body in self.files.items():
            self.assertFalse(path.endswith((".py",".toml",".zip")))
            self.assertNotIn("..",Path(path).parts)
            self.assertFalse(path.startswith("/"))
            if path.endswith((".html",".json")):
                self.assertNotIn(b"/Users/",body)
                self.assertNotIn(b"/workspace/",body)

    def test_tampered_snapshot_is_rejected_before_it_can_execute(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/"snapshot"
            source=ARCHIVE_ROOT/ARCHIVED_ITERATIONS[0]["slug"]
            shutil.copytree(source,destination)
            manifest=json.loads((destination/"manifest.json").read_text())
            target=destination/"source"/manifest["files"][0]["path"]
            target.write_bytes(target.read_bytes()+b"\n# altered\n")
            with self.assertRaisesRegex(ValueError,"digest"):
                verify_source_archive(destination)

    def test_unlisted_source_cannot_be_imported_by_a_historical_build(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/"snapshot"
            source=ARCHIVE_ROOT/ARCHIVED_ITERATIONS[0]["slug"]
            shutil.copytree(source,destination)
            (destination/"source/src/unlisted.py").write_text("raise RuntimeError('unexpected source')\n")
            with self.assertRaisesRegex(ValueError,"unlisted"):
                verify_source_archive(destination)

class IterationCatalogTests(unittest.TestCase):
    def test_catalog_contains_real_older_interfaces_and_correct_editor_entrypoints(self):
        by_slug={item["slug"]:item for item in ENGINEERED_ITERATIONS}
        for slug in ("studio-authored","studio-strips","studio-instant","modular-lab",
                     "modular-continuous","modular-preload","modular-integrated"):
            self.assertEqual(by_slug[slug]["url"],f"iterations/{slug}/")
        for slug in ("effects-lab","arrangement-editor","panel-workspace"):
            self.assertTrue(by_slug[slug]["url"].endswith("/lab.html"))
        self.assertEqual(len(by_slug),len(ENGINEERED_ITERATIONS))
        self.assertFalse(any("youtube" in str(item).lower() for item in ENGINEERED_ITERATIONS))
