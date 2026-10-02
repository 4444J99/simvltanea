"""Exercise operational paths across workflow boundaries."""
import importlib
from pathlib import Path
import unittest

from tools.paths import REPO_ROOT, VAR_DIR, WORK_DIR, SITE_DIR, PACKAGES_DIR


class PathContractTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
