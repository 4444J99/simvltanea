"""Hermetic staging failures must never mix executable bytes and HTML receipts."""
from __future__ import annotations

import hashlib
import shutil
import unittest
from pathlib import Path
import stat
import os
import subprocess
from unittest.mock import patch

from simvltanea.browser import browser_runtime as runtime
from simvltanea.browser.shared_engine import SharedEngineUnavailable
from simvltanea.browser.test_shared_engine import HermeticEngineFixture


class PreviewStagingTest(HermeticEngineFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.generated = self.fixture_root / 'var'
        self.generated.mkdir()
        self.output = self.generated / 'preview'
        self.state = self.fixture_root / 'input' / 'state.json'
        self.state.parent.mkdir()
        self.state.write_text('{}')
        # macOS exposes /var through /private/var; compare canonical paths just
        # as build_preview does for the destination, preserving containment.
        self.enterContext(patch.object(runtime, 'REPO_ROOT', self.fixture_root.resolve()))
        self.enterContext(patch.object(runtime, 'LAYOUT'))
        runtime.LAYOUT.path.return_value = self.generated.resolve()
        self.enterContext(patch.object(runtime, 'resolve_shared_engine', return_value=self.engine))

    def build_generation(self, state, output):
        receipt = runtime.stage_shared_engine(output)
        (output / 'index.html').write_text(f'verified {receipt["files_verified"]}')
        return receipt

    def build(self):
        with patch.object(runtime, '_build_preview_generation', side_effect=self.build_generation):
            return runtime.build_preview(self.state, self.output)

    def snapshot(self):
        return {p.relative_to(self.output).as_posix(): p.read_bytes()
                for p in self.output.rglob('*') if p.is_file()}

    def test_untracked_files_are_excluded_and_staged_digests_match(self):
        (self.engine.module_root / 'src' / 'untracked.js').write_text('unaccepted')
        receipt = self.build()
        staged = self.output / 'shared-engine'
        self.assertEqual({p.relative_to(self.output).as_posix() for p in staged.rglob('*') if p.is_file()},
                         set(self.pin['runtime_graph']))
        for relative, digest in self.pin['runtime_graph'].items():
            self.assertEqual(hashlib.sha256((self.output / relative).read_bytes()).hexdigest(), digest)
        self.assertEqual(receipt['files_verified'], len(self.pin['runtime_graph']))

    def test_checkout_mutation_during_copy_preserves_existing_preview(self):
        self.build()
        before = self.snapshot()
        copyfile = shutil.copyfile
        def mutate(source, target, *args, **kwargs):
            if source == self.engine.entrypoint:
                source.write_text('mutated after resolution')
            return copyfile(source, target, *args, **kwargs)
        with patch.object(runtime.shutil, 'copyfile', side_effect=mutate):
            with self.assertRaises(SharedEngineUnavailable):
                self.build()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.generated.glob('.preview-stage-*')), [])

    def test_destination_mutation_is_detected_even_when_source_still_matches(self):
        copyfile = shutil.copyfile
        def corrupt(source, target, *args, **kwargs):
            result = copyfile(source, target, *args, **kwargs)
            if source == self.engine.entrypoint:
                Path(target).write_text('corrupt staged bytes')
            return result
        with patch.object(runtime.shutil, 'copyfile', side_effect=corrupt):
            with self.assertRaises(SharedEngineUnavailable):
                self.build()
        self.assertFalse(self.output.exists())
        self.engine.verify()  # Original bytes remain valid; source recheck would miss it.

    def test_copy_failure_preserves_existing_preview(self):
        self.build()
        before = self.snapshot()
        with patch.object(runtime.shutil, 'copyfile', side_effect=OSError('copy failed')):
            with self.assertRaisesRegex(OSError, 'copy failed'):
                self.build()
        self.assertEqual(self.snapshot(), before)

    def test_failed_atomic_exchange_preserves_existing_preview(self):
        self.build()
        before = self.snapshot()
        with patch.object(runtime.ctypes, 'CDLL') as libc:
            libc.return_value.renameat2.return_value = -1
            libc.return_value.renamex_np.return_value = -1
            with patch.object(runtime.ctypes, 'get_errno', return_value=5):
                with self.assertRaises(OSError):
                    self.build()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(self.generated.glob('.preview-stage-*')), [])

    def test_existing_preview_is_replaced_as_one_generation(self):
        self.build()
        (self.output / 'stale.js').write_text('old generation')
        self.build()
        self.assertFalse((self.output / 'stale.js').exists())
        self.assertTrue((self.output / 'index.html').exists())
        kept = list(self.generated.glob('.preview-retained-*'))
        self.assertEqual(len(kept), 1)
        self.assertEqual((kept[0] / 'generation' / 'stale.js').read_text(), 'old generation')
        self.assertEqual(stat.S_IMODE(kept[0].stat().st_mode), 0o700)
        self.assertEqual(list(self.generated.glob('.preview-stage-*')), [])

    def test_resolution_failure_replaces_receipt_with_clean_fallback(self):
        self.build()
        def fallback(state, output):
            self.assertIsNone(runtime.stage_shared_engine(output))
            (output / 'index.html').write_text('unavailable')
            return {}
        with patch.object(runtime, 'resolve_shared_engine', side_effect=SharedEngineUnavailable('rejected')):
            with patch.object(runtime, '_build_preview_generation', side_effect=fallback):
                runtime.build_preview(self.state, self.output)
        self.assertEqual(set(self.snapshot()), {'index.html', 'shared-engine-unavailable.txt', runtime.PREVIEW_MARKER})
        self.assertEqual((self.output / 'index.html').read_text(), 'unavailable')

    def test_reused_or_symlinked_staging_destination_is_rejected(self):
        self.output.mkdir()
        external = self.fixture_root / 'external'
        external.write_text('preserve')
        (self.output / 'shared-engine-adapter.js').symlink_to(external)
        with self.assertRaises(ValueError):
            runtime.stage_shared_engine(self.output)
        with self.assertRaises(runtime.c.StateError):
            self.build()
        self.assertEqual(external.read_text(), 'preserve')

    def test_publication_permissions_match_mkdir_and_preserve_existing_mode(self):
        probe = self.generated / 'normal'
        probe.mkdir()
        self.build()
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), stat.S_IMODE(probe.stat().st_mode))
        self.output.chmod(0o750)
        self.build()
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o750)

    def test_repository_and_unowned_generated_directories_are_preserved(self):
        for target in (self.fixture_root / 'src', self.generated / 'personal-media'):
            target.mkdir()
            (target / 'preserve').write_text('irreplaceable')
            with self.subTest(target=target):
                with patch.object(self, 'output', target):
                    with self.assertRaises(runtime.c.StateError):
                        self.build()
            self.assertEqual((target / 'preserve').read_text(), 'irreplaceable')

    def test_tracked_generated_files_are_preserved(self):
        self.build()
        before = self.snapshot()
        (self.fixture_root / '.git').mkdir()
        from subprocess import CompletedProcess
        with patch.object(runtime.subprocess, 'run', return_value=CompletedProcess([], 0, stdout=b'tracked')):
            with self.assertRaisesRegex(runtime.c.StateError, 'tracked'):
                self.build()
        self.assertEqual(self.snapshot(), before)

    def test_non_checkout_preview_does_not_require_git(self):
        with patch.object(runtime.subprocess, 'run', side_effect=FileNotFoundError('no Git')) as run:
            self.build()
        run.assert_not_called()
        self.assertTrue((self.output / 'index.html').is_file())

    def test_checkout_guard_fails_closed_without_git(self):
        self.build()
        before = self.snapshot()
        (self.fixture_root / '.git').mkdir()
        with patch.object(runtime.subprocess, 'run', side_effect=FileNotFoundError('no Git')):
            with self.assertRaisesRegex(runtime.c.StateError, 'tracked-file protection'):
                self.build()
        self.assertEqual(self.snapshot(), before)

    def test_non_object_owner_manifest_is_a_refusal(self):
        from simvltanea.browser.shared_engine import resolve_shared_engine
        for value in ('[]', 'null', '"text"'):
            with self.subTest(value=value):
                (self.engine.module_root / 'PROVENANCE.json').write_text(value)
                with self.assertRaisesRegex(SharedEngineUnavailable, 'JSON object'):
                    resolve_shared_engine(self.start, pin=self.pin)

    def test_destination_created_during_staging_is_preserved(self):
        generation = self.build_generation
        def raced(state, staging):
            result = generation(state, staging)
            self.output.mkdir()
            (self.output / 'personal').write_text('preserve')
            return result
        with patch.object(self, 'build_generation', side_effect=raced):
            with self.assertRaises((OSError, runtime.c.StateError)):
                self.build()
        self.assertEqual((self.output / 'personal').read_text(), 'preserve')
        self.assertFalse((self.output / 'index.html').exists())

    def test_no_clobber_publication_rejects_last_moment_creation(self):
        rename = runtime._rename_preview
        def raced(staging, output, *, exchange):
            self.assertFalse(exchange)
            output.mkdir()
            (output / 'personal').write_text('preserve')
            rename(staging, output, exchange=exchange)
        with patch.object(runtime, '_rename_preview', side_effect=raced):
            with self.assertRaises(FileExistsError):
                self.build()
        self.assertEqual((self.output / 'personal').read_text(), 'preserve')

    def _race_existing_exchange(self, rollback_fails=False):
        self.build()
        before = self.snapshot()
        old = self.generated / 'retained-original'
        rename = runtime._rename_preview
        calls = 0
        def raced(staging, output, *, exchange):
            nonlocal calls
            calls += 1
            self.assertTrue(exchange)
            if calls == 1:
                output.rename(old)
                output.mkdir()
                (output / 'personal').write_text('preserve')
            elif rollback_fails:
                raise OSError('rollback refused')
            rename(staging, output, exchange=True)
        with patch.object(runtime, '_rename_preview', side_effect=raced):
            with self.assertRaises(OSError):
                self.build()
        self.assertEqual(before, {p.relative_to(old).as_posix():p.read_bytes()
                                  for p in old.rglob('*') if p.is_file()})
        return old

    def test_destination_swap_during_exchange_is_restored(self):
        self._race_existing_exchange()
        self.assertEqual((self.output / 'personal').read_text(), 'preserve')
        self.assertEqual(list(self.generated.glob('.preview-stage-*')), [])

    def test_failed_rollback_preserves_the_displaced_directory(self):
        self._race_existing_exchange(rollback_fails=True)
        kept = list(self.generated.glob('.preview-retained-*'))
        self.assertEqual(len(kept), 1)
        self.assertEqual((kept[0] / 'generation' / 'personal').read_text(), 'preserve')
        self.assertEqual((self.output / 'index.html').read_text(), 'verified 6')

    def test_git_environment_cannot_hide_real_tracked_files(self):
        self.build()
        subprocess.run(['git', 'init', '-q', str(self.fixture_root)], check=True)
        subprocess.run(['git', '-C', str(self.fixture_root), 'add', '-f', 'var/preview/index.html'], check=True)
        unrelated = self.fixture_root / 'unrelated'
        subprocess.run(['git', 'init', '-q', str(unrelated)], check=True)
        before = self.snapshot()
        with patch.dict(os.environ, {'GIT_DIR':str(unrelated / '.git'),
                                     'GIT_WORK_TREE':str(unrelated),
                                     'GIT_INDEX_FILE':str(unrelated / '.git' / 'alternate-index')}):
            with self.assertRaisesRegex(runtime.c.StateError, 'tracked files'):
                self.build()
        self.assertEqual(before, self.snapshot())

    def test_tracked_output_names_are_literal_paths(self):
        self.output = self.generated / 'preview[own]'
        self.build()
        subprocess.run(['git', 'init', '-q', str(self.fixture_root)], check=True)
        subprocess.run(['git', '-C', str(self.fixture_root), 'add', '-f', 'var/preview[own]/index.html'], check=True)
        before = self.snapshot()
        with self.assertRaisesRegex(runtime.c.StateError, 'tracked files'):
            self.build()
        self.assertEqual(before, self.snapshot())

    def test_late_index_change_rolls_back_without_deleting_tracked_preview(self):
        self.build()
        before = self.snapshot()
        subprocess.run(['git', 'init', '-q', str(self.fixture_root)], check=True)
        rename = runtime._rename_preview
        calls = 0
        def track_after_exchange(staging, output, *, exchange):
            nonlocal calls
            calls += 1
            rename(staging, output, exchange=exchange)
            if calls == 1:
                subprocess.run(['git', '-C', str(self.fixture_root), 'add', '-f', 'var/preview/index.html'], check=True)
        with patch.object(runtime, '_rename_preview', side_effect=track_after_exchange):
            with self.assertRaisesRegex(runtime.c.StateError, 'tracked files'):
                self.build()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(list(self.generated.glob('.preview-stage-*')), [])


class SafeStagingAndPreviewLabellingTests(unittest.TestCase):
    def test_safe_staging_collision_refusal_on_unprovenanced_nonempty_directory(self):
        from tools.media import import_photos
        from tools.editions import build_edition
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "staged"
            out_dir.mkdir()
            (out_dir / "unrelated.mp4").write_text("foreign media")
            proj_path = Path(tmpdir) / "project.json"
            lib_path = Path(tmpdir) / "Photos.photoslibrary"

            # import_photos provenance check fails on unprovenanced directory
            self.assertFalse(
                import_photos.verify_staging_provenance(out_dir, proj_path, lib_path, {})
            )
            # build_edition provenance check fails on unprovenanced directory
            self.assertFalse(
                build_edition.verify_edition_provenance(out_dir, proj_path, "test-edition")
            )

    def test_safe_staging_provenance_verified_with_matching_staging_manifest(self):
        from tools.media import import_photos
        from tools.editions import build_edition
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "staged"
            out_dir.mkdir()
            (out_dir / "valid_clip.mp4").write_text("valid clip")
            proj_path = Path(tmpdir) / "project.json"
            lib_path = Path(tmpdir) / "Photos.photoslibrary"

            import_photos.write_staging_manifest(out_dir, lib_path, {"album": ["test"]}, 1, dry_run=False)
            self.assertTrue(
                import_photos.verify_staging_provenance(out_dir, proj_path, lib_path, {"album": ["test"]})
            )

            build_edition.write_staging_manifest(out_dir, "my-slug", dry_run=False)
            self.assertTrue(
                build_edition.verify_edition_provenance(out_dir, proj_path, "my-slug")
            )

    def test_prepare_output_dir_never_destructively_empties_active_staging(self):
        from tools.media import import_photos
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "staged"
            out_dir.mkdir()
            canary = out_dir / "staged_001.mov"
            canary.write_text("precious staged bytes")

            import_photos.prepare_output_dir(out_dir, keep_existing=False, dry_run=False)
            self.assertTrue(canary.exists())
            self.assertEqual(canary.read_text(), "precious staged bytes")

    def test_photos_library_protection_refuses_staging_inside_photos(self):
        from tools.media import import_photos
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            lib_path = Path(tmpdir) / "Photos.photoslibrary"
            lib_path.mkdir()
            out_dir = lib_path / "inside_photos"
            self.assertTrue(import_photos.path_inside(out_dir, lib_path))

    def test_build_edition_bounded_preview_labelling(self):
        from tools.editions import build_edition
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(build_edition, "SCRIPT_DIR", root):
                proj_path = root / "project.json"
                proj_path.write_text("{}")
                edition = {
                    "name": "Bounded Edition",
                    "slug": "bounded-edition",
                    "_cli_limit": 8,
                    "source": {"type": "photos_album", "limit": 8},
                }
                project = build_edition.apply_edition_settings(proj_path, edition, dry_run=False)
                self.assertEqual(project["edition"]["coverage_mode"], "bounded_preview")
                self.assertEqual(project["edition"]["preview_limit"], 8)
                self.assertFalse(project["edition"]["full_album_complete"])
                self.assertEqual(project["coverage_mode"], "bounded_preview")
                self.assertEqual(project["preview_limit"], 8)
                self.assertFalse(project["full_album_complete"])

    def test_build_edition_full_album_labelling(self):
        from tools.editions import build_edition
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.object(build_edition, "SCRIPT_DIR", root):
                proj_path = root / "project.json"
                proj_path.write_text('{"photos_import":{"coverage_mode":"full","preview_limit":null,"full_album_complete":true,"selection":{"limit":null,"offset":0}}}')
                edition = {
                    "name": "Full Edition",
                    "slug": "full-edition",
                    "source": {"type": "photos_album", "all_local": True},
                }
                project = build_edition.apply_edition_settings(proj_path, edition, dry_run=False)
                self.assertEqual(project["edition"]["coverage_mode"], "full")
                self.assertTrue(project["edition"]["full_album_complete"])
                self.assertEqual(project["coverage_mode"], "full")
                self.assertTrue(project["full_album_complete"])

    def test_import_photos_bounded_preview_labelling(self):
        from tools.media import import_photos
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            base_proj = Path(tmpdir) / "base.json"
            base_proj.write_text("{}")
            local_proj = Path(tmpdir) / "local.json"
            out_dir = Path(tmpdir) / "staged"
            out_dir.mkdir()
            lib_path = Path(tmpdir) / "Photos.photoslibrary"

            import_photos.write_local_project(
                base_project_path=base_proj,
                local_project_path=local_proj,
                output_dir=out_dir,
                items=[],
                mode="copy",
                library=lib_path,
                photos_export_missing=False,
                selection={"order": "oldest", "limit": 12},
                dry_run=False,
            )
            saved = json.loads(local_proj.read_text(encoding="utf-8"))
            self.assertEqual(saved["photos_import"]["coverage_mode"], "bounded_preview")
            self.assertEqual(saved["photos_import"]["preview_limit"], 12)
            self.assertFalse(saved["photos_import"]["full_album_complete"])
            self.assertEqual(saved["coverage_mode"], "bounded_preview")
            self.assertEqual(saved["preview_limit"], 12)
            self.assertFalse(saved["full_album_complete"])


class ReviewRegressionTests(unittest.TestCase):
    def test_repeat_symlink_staging_preserves_original(self):
        from tools.media import import_photos as p
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); library=root/'Photos.photoslibrary'; library.mkdir()
            original=library/'original.mov'; original.write_bytes(b'original')
            staged=root/'staged'; staged.mkdir(); dest=staged/'clip.mov'
            asset=p.Asset(1,'stable-source',None,None,1.,10,10,'original.mov',None,0)
            item=p.ImportItem(asset,original,dest,False)
            for _ in range(2):
                p.stage_media([item],'symlink',False,root/'work',library=library)
            self.assertTrue(dest.is_symlink())
            self.assertEqual(original.read_bytes(), b'original')
            alias=root/'alias'; alias.symlink_to(library, target_is_directory=True)
            with self.assertRaises(SystemExit):
                p.stage_media([p.ImportItem(asset,original,alias/'other.mov',False)],'copy',False,root/'work',library=library)
            self.assertFalse((library/'other.mov').exists())

    def test_provenance_requires_library_and_destination(self):
        from tools.media import import_photos as p
        from tools.editions import build_edition as e
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'out'; out.mkdir(); project=root/'project.json'
            library=root/'Photos.photoslibrary'
            for metadata in ({'edition':{'slug':'same'}},
                             {'edition':{'slug':'same'},'photos_import':{'library':str(library)},'input_dir':'elsewhere'}):
                project.write_text(json.dumps(metadata))
                self.assertFalse(p.verify_staging_provenance(out,project,library,{}))
                self.assertFalse(e.verify_edition_provenance(out,project,'same'))
            project.write_text(json.dumps({'edition':{'slug':'same'},'photos_import':{'library':str(library)},'input_dir':'out'}))
            self.assertTrue(p.verify_staging_provenance(out,project,library,{}))
            self.assertTrue(e.verify_edition_provenance(out,project,'same'))

    def test_reused_bounded_import_cannot_be_promoted(self):
        from tools.editions import build_edition as e
        import tempfile
        from unittest.mock import patch
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); project=root/'project.json'
            project.write_text(json.dumps({'photos_import':{'coverage_mode':'bounded_preview', 'preview_limit':8,'full_album_complete':False,'selection':{'limit':8}}}))
            with patch.object(e,'SCRIPT_DIR',root):
                value=e.apply_edition_settings(project,{'slug':'live','source':{'type':'photos_album','all_local':True}},False)
            self.assertEqual(value['coverage_mode'],'bounded_preview')
            self.assertEqual(value['preview_limit'],8)
            self.assertFalse(value['edition']['full_album_complete'])

    def test_default_photos_limit_is_bounded(self):
        from tools.editions import build_edition as e
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); project=root/'project.json'; project.write_text('{}')
            with patch.object(e,'SCRIPT_DIR',root):
                value=e.apply_edition_settings(project,{'slug':'live','source':{'type':'photos_album'}},False)
            self.assertEqual(value['coverage_mode'],'bounded_preview')
            self.assertEqual(value['preview_limit'],12)
            self.assertFalse(value['full_album_complete'])

    def test_offset_import_is_partial_without_limit(self):
        from tools.media import import_photos as p
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=root/'base.json'; base.write_text('{}'); project=root/'project.json'
            p.write_local_project(base,project,root/'out',[],'copy',root/'Photos.photoslibrary',False,{'limit':None,'offset':20},False)
            value=json.loads(project.read_text())
            self.assertEqual(value['coverage_mode'],'bounded_preview')
            self.assertFalse(value['photos_import']['full_album_complete'])

    def test_copied_staging_markers_do_not_authorize_new_destination(self):
        from tools.media import import_photos as p
        from tools.editions import build_edition as e
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'out'; out.mkdir(); other=root/'other'; other.mkdir()
            library=root/'Photos.photoslibrary'; project=root/'absent.json'
            p.write_staging_manifest(out,library,{},1,False)
            (other/'.staging_manifest.json').write_bytes((out/'.staging_manifest.json').read_bytes())
            self.assertFalse(p.verify_staging_provenance(other,project,library,{}))
            e.write_staging_manifest(out,'live',False)
            (other/'.staging_manifest.json').write_bytes((out/'.staging_manifest.json').read_bytes())
            self.assertFalse(e.verify_edition_provenance(other,project,'live'))

    def test_edition_manifest_preserves_photos_provenance_for_reimport(self):
        from tools.media import import_photos as p
        from tools.editions import build_edition as e
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'out'; out.mkdir(); library=root/'Photos.photoslibrary'
            p.write_staging_manifest(out,library,{},1,False)
            e.write_staging_manifest(out,'live',False)
            self.assertTrue(p.verify_staging_provenance(out,root/'absent.json',library,{}))
            p.write_staging_manifest(out,library,{},1,False)
            self.assertTrue(e.verify_edition_provenance(out,root/'absent.json','live'))

    def test_all_local_preset_without_import_evidence_is_not_complete(self):
        from tools.editions import build_edition as e
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); project=root/'project.json'; project.write_text('{}')
            with patch.object(e,'SCRIPT_DIR',root):
                value=e.apply_edition_settings(project,{'slug':'live','source':{'type':'photos_album','all_local':True}},False)
            self.assertFalse(value['full_album_complete'])
            self.assertEqual(value['coverage_mode'],'unknown')

    def test_missing_originals_cannot_claim_full_album(self):
        from tools.media import import_photos as p
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=root/'base.json'; base.write_text('{}'); project=root/'project.json'
            p.write_local_project(base,project,root/'out',[],'copy',root/'Photos.photoslibrary',False,
                                  {'limit':None,'offset':0,'missing_local_count':1},False)
            value=json.loads(project.read_text())
            self.assertFalse(value['photos_import']['full_album_complete'])
            self.assertFalse(value['full_album_complete'])

    def test_unknown_coverage_is_stable_across_reapplication(self):
        from tools.editions import build_edition as e
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'project.json'; path.write_text('{}')
            edition={'slug':'live','source':{'type':'photos_album','all_local':True}}
            with patch.object(e,'SCRIPT_DIR',root):
                for _ in range(2):
                    value=e.apply_edition_settings(path,edition,False)
                    self.assertEqual(value['coverage_mode'],'unknown')
                    self.assertFalse(value['full_album_complete'])

    def test_filtered_imports_do_not_claim_full_album(self):
        from tools.media import import_photos as p
        import tempfile
        import json
        cases=({'start_date':'2026-01-01'}, {'end_date':'2026-02-01'},
               {'excluded_uuid_count':1}, {'duration_filtered_count':1})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); base=root/'base.json'; base.write_text('{}'); project=root/'project.json'
            for extra in cases:
                with self.subTest(selection=extra):
                    p.write_local_project(base,project,root/'out',[],'copy',root/'Photos.photoslibrary',False,
                                          {'limit':None,'offset':0,**extra},False)
                    value=json.loads(project.read_text())
                    self.assertFalse(value['full_album_complete'])
                    self.assertEqual(value['coverage_mode'],'bounded_preview')
            p.write_local_project(base,project,root/'out',[],'copy',root/'Photos.photoslibrary',False,
                                  {'limit':None,'max_duration':45,'duration_filtered_count':0},False)
            self.assertTrue(json.loads(project.read_text())['full_album_complete'])

    def test_duration_filter_counts_actual_omissions_and_preserves_live_photos(self):
        from tools.media import import_photos as p
        def asset(name,duration,style=4):
            return p.Asset(1,name,None,None,duration,10,10,name,None,style)
        clips=[asset('short',1),asset('long',60),asset('live',0,3)]
        selected=p.duration_filtered_assets(clips,.1,45)
        self.assertEqual([x.uuid for x in selected],['short','live'])
        self.assertEqual(len(clips)-len(selected),1)
        self.assertEqual(p.duration_filtered_assets(clips,.1,0),clips)

    def test_cli_records_album_duration_omissions_with_real_sqlite_catalog(self):
        from tools.media import import_photos as p
        from unittest.mock import patch
        import tempfile
        import sqlite3
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); library=root/'Photos.photoslibrary'; library.mkdir()
            database=library/'database'; database.mkdir(); db=database/'Photos.sqlite'
            short='11111111-1111-1111-1111-111111111111'
            long='22222222-2222-2222-2222-222222222222'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE ZASSET (Z_PK, ZUUID, ZDATECREATED, ZADDEDDATE, ZDURATION, ZWIDTH, ZHEIGHT, ZFILENAME, ZPLAYBACKSTYLE, ZTRASHEDSTATE, ZHIDDEN, ZVISIBILITYSTATE)')
                conn.execute('CREATE TABLE ZADDITIONALASSETATTRIBUTES (ZASSET, ZORIGINALFILENAME)')
                for i,(identity,duration) in enumerate(((short,1),(long,60)),1):
                    conn.execute('INSERT INTO ZASSET VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                 (i,identity,1,1,duration,10,10,identity+'.mov',4,0,0,0))
                    (library/(identity+'.mov')).write_bytes(identity.encode())
            base=root/'base.json'; base.write_text('{}'); project=root/'project.json'
            argv=['import_photos','--library',str(library),'--source-project',str(base),
                  '--project',str(project),'--output-dir',str(root/'out'),
                  '--photos-export-work-dir',str(root/'work'),'--exclude-file',str(root/'exclude'),
                  '--all-local']
            with patch.object(p,'SCRIPT_DIR',root),patch.object(p.sys,'argv',argv):
                self.assertEqual(p.main(),0)
                value=json.loads(project.read_text())
                self.assertEqual(value['photos_import']['selection']['duration_filtered_count'],1)
                self.assertEqual(len(value['clips']),1)
                self.assertFalse(value['full_album_complete'])
                with sqlite3.connect(db) as conn:
                    conn.execute('DELETE FROM ZASSET WHERE ZUUID=?',(long,))
                self.assertEqual(p.main(),0)
                value=json.loads(project.read_text())
                self.assertEqual(value['photos_import']['selection']['duration_filtered_count'],0)
                self.assertTrue(value['full_album_complete'])
            for identity in (short,long):
                self.assertEqual((library/(identity+'.mov')).read_bytes(),identity.encode())
