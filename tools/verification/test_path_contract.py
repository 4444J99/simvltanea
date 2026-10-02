"""Exercise operational paths across workflow boundaries."""
import importlib
from pathlib import Path
import unittest

from tools.paths import REPO_ROOT, VAR_DIR, WORK_DIR, SITE_DIR, PACKAGES_DIR


class PathContractTests(unittest.TestCase):
    def test_compatibility_modules_share_canonical_implementations(self):
        for old, new in (
            ("composition", "authoring.composition"),
            ("composition_model", "authoring.composition_model"),
            ("artifact001_layouts", "authoring.artifact001_layouts"),
            ("browser_runtime", "browser.browser_runtime"),
            ("render_triptych", "rendering.render_triptych"),
            ("make_runtime_fixture", "generators.make_runtime_fixture"),
        ):
            with self.subTest(module=old):
                canonical = importlib.import_module("simvltanea." + new)
                self.assertIs(importlib.import_module("simvltanea." + old), canonical)
                # Bare imports were a historical PYTHONPATH=src/simvltanea interface.
                import sys
                from unittest.mock import patch
                with patch.object(sys, "path", [str(REPO_ROOT / "src" / "simvltanea"), *sys.path]):
                    self.assertIs(importlib.import_module(old), canonical)

    def test_browser_assets_follow_the_runtime_package(self):
        from importlib.resources import files
        from simvltanea.browser import browser_runtime
        for name in ("browser.runtime.js", "browser.continuity.js"):
            self.assertTrue(files("simvltanea.browser").joinpath(name).is_file())
            self.assertTrue((browser_runtime.HERE / name).is_file())

    def test_shadow_output_directories_are_rejected_by_governance(self):
        from tools.verification import verify_repository_structure as structure
        for path in ('tools/work/project.json', 'tools/media/site/index.html',
                     'src/simvltanea/renders/output.mp4'):
            with self.subTest(path=path):
                self.assertTrue(structure.is_generated_path(path))
                self.assertIsNotNone(structure.path_violation(path))

    def test_command_output_defaults_stay_under_var(self):
        for path in (REPO_ROOT / 'tools').glob('*/*.py'):
            if path.name == '__init__.py':
                continue
            name = '.'.join(path.relative_to(REPO_ROOT).with_suffix('').parts)
            module = importlib.import_module(name)
            for key, value in vars(module).items():
                if key.startswith('DEFAULT_') and isinstance(value, Path) and (
                    key.endswith(('_OUTPUT', '_OUTPUT_DIR', '_SITE_DIR', '_PACKAGE_DIR',
                                  '_LOCAL_PROJECT', '_CATALOG', '_EXCLUDE_FILE',
                                  '_DOC', '_HTML', '_SUMMARY', '_CHUNK_DIR'))
                ):
                    with self.subTest(command=name, default=key):
                        self.assertTrue(value.resolve().is_relative_to(VAR_DIR))

    def test_public_workflows_accept_canonical_output_directories(self):
        from tools.publishing import package_public_site, build_site_index
        from tools.verification import verify_package, verify_post_pack
        from tools.media import import_folder
        import_folder.require_inside(WORK_DIR / 'editions/test/project.json',
                                     REPO_ROOT, 'project')
        for module in (package_public_site, build_site_index, verify_package, verify_post_pack):
            with self.subTest(command=module.__name__):
                self.assertTrue(module.path_inside(SITE_DIR, module.SCRIPT_DIR))
                self.assertTrue(module.path_inside(PACKAGES_DIR, module.SCRIPT_DIR))

    def test_edition_import_command_runs_as_a_module(self):
        from tools.editions import build_edition
        command = build_edition.render_command(WORK_DIR / 'project.json', True, [], True)
        self.assertEqual(command[1:3], ['-m', 'tools.editions.export_project'])

    def test_media_recipe_lookup_includes_canonical_template(self):
        from tools.media import atomize_media
        self.assertTrue(atomize_media.load_project_recipes())
        self.assertEqual(atomize_media.ROOT, VAR_DIR)

    def test_layout_manifest_is_idempotent(self):
        """Identical manifest inputs produce identical Layout role and policy mappings."""
        from simvltanea.paths import REPO_ROOT, load_layout, LAYOUT
        layout2 = load_layout(REPO_ROOT)
        self.assertEqual(dict(layout2.roles), dict(LAYOUT.roles))
        self.assertEqual(dict(layout2.policy), dict(LAYOUT.policy))
        self.assertEqual(dict(layout2.contract), dict(LAYOUT.contract))

    def test_layout_contract_version_is_semver(self):
        """Layout manifest carries a three-part numeric contract version."""
        from simvltanea.paths import LAYOUT
        version = LAYOUT.contract.get("version", "")
        self.assertTrue(version, "contract.version is absent from layout.toml")
        parts = version.split(".")
        self.assertEqual(len(parts), 3, f"not major.minor.patch: {version!r}")
        self.assertTrue(
            all(p.isdigit() for p in parts),
            f"non-numeric parts in contract version: {version!r}",
        )

    def test_invalid_layout_contract_version_is_rejected(self):
        """load_layout raises ValueError for non-semver contract.version values."""
        import tempfile
        from pathlib import Path
        from simvltanea.paths import LAYOUT, load_layout
        original = LAYOUT.manifest.read_text()
        # Strip any existing [contract] block so we can inject a known-bad one.
        stripped = "\n".join(
            line for line in original.splitlines()
            if not line.startswith("[contract]") and not line.startswith("version =")
        )
        with tempfile.TemporaryDirectory() as d:
            manifest = Path(d) / "layout.toml"
            for bad_version in ("1.0", "v1.0.0", "1.0.0-alpha", "not-a-version"):
                with self.subTest(version=bad_version):
                    manifest.write_text(
                        stripped + f'\n[contract]\nversion = "{bad_version}"\n'
                    )
                    with self.assertRaises(ValueError):
                        load_layout(LAYOUT.root, manifest)


if __name__ == '__main__':
    unittest.main()
