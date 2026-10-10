"""Hermetic staging failures must never mix executable bytes and HTML receipts."""
from __future__ import annotations

import hashlib
import shutil
import unittest
from pathlib import Path
import stat
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
