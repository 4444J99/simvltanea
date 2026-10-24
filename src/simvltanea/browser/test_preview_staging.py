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
                proj_path.write_text("{}")
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
