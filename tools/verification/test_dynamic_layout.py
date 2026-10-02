"""Exercise real commands and governance with a different physical hierarchy."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


from simvltanea.paths import LAYOUT, REPO_ROOT, load_layout, resolve_references


class DynamicLayoutTests(unittest.TestCase):
    def alternate_manifest(self, root: Path) -> Path:
        text = LAYOUT.manifest.read_text()
        replacements = {
            'generated': 'local/cache', 'work': 'local/cache/private/state',
            'samples': 'local/cache/intake', 'renders': 'local/cache/video',
            'site': 'local/cache/web', 'packages': 'local/cache/distribution',
            'proofs': 'local/cache/review', 'artifact_output': 'local/cache/engineering',
            'examples': 'inputs/templates', 'fixtures': 'inputs/regression',
            'artifact_fixture': 'inputs/regression/artifact-001',
            'editions': 'content/editions', 'registry': 'content/editions/index.json',
        }
        for role, value in replacements.items():
            text = text.replace(f'{role} = "{LAYOUT.relative(role)}"', f'{role} = "{value}"')
        manifest = root / 'src/simvltanea/layout.toml'
        manifest.parent.mkdir(parents=True)
        manifest.write_text(text)
        return manifest

    def test_commands_templates_inventory_and_governance_follow_relocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.alternate_manifest(root)
            layout = load_layout(root, manifest)
            original = manifest.read_bytes()
            for relative in layout.policy_paths('required_files'):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('')
            manifest.write_bytes(original)
            for relative in layout.policy_paths('required_directories'):
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root/'evidence/visual-proof/frames/review.png').write_bytes(b'proof')
            for example in LAYOUT.path('examples').glob('*.json'):
                (layout.path('examples')/example.name).write_bytes(example.read_bytes())
            layout.path('registry').write_bytes(LAYOUT.path('registry').read_bytes())
            for name in ('ls-lint.yml', 'markdownlintignore'):
                (root/'config/lint'/name).write_bytes((REPO_ROOT/'config/lint'/name).read_bytes())
            env = dict(os.environ, SIMVLTANEA_ROOT=str(root), SIMVLTANEA_LAYOUT=str(manifest),
                       PYTHONPATH=os.pathsep.join((str(REPO_ROOT), str(REPO_ROOT/'src'))),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
            program = r'''
import importlib, json, subprocess
from pathlib import Path
from tools.paths import *
from tools.verification import sync_layout, verify_repository_structure as structure
from tools.preservation import generated_inventory, overnight_checkpoint
from tools.media import atomize_media
from tools.editions import build_edition
from tools.verification import verify_editions
assert sync_layout.main(['--write']) == 0
assert sync_layout.main([]) == 0
subprocess.run(['git','init','--quiet',str(REPO_ROOT)],check=True)
subprocess.run(['git','-C',str(REPO_ROOT),'add','-A'],check=True)
assert structure.verify_structure(REPO_ROOT) == [], structure.verify_structure(REPO_ROOT)
for file in (Path(__import__('tools').__file__).parent).glob('*/*.py'):
    if file.name == '__init__.py': continue
    module = importlib.import_module('tools.' + file.parent.name + '.' + file.stem)
    for key,value in vars(module).items():
        if key.startswith('DEFAULT_') and isinstance(value,Path) and key.endswith(('_OUTPUT','_OUTPUT_DIR','_SITE_DIR','_PACKAGE_DIR','_LOCAL_PROJECT','_CATALOG','_EXCLUDE_FILE','_DOC','_HTML','_SUMMARY','_CHUNK_DIR')):
            assert value.is_relative_to(VAR_DIR), (module.__name__,key,value)
assert build_edition.DEFAULT_EDITIONS == EDITIONS_FILE
registry = build_edition.load_json(EDITIONS_FILE)
assert registry['default_source_project'] == str(EXAMPLES_DIR/'project.example.json')
inaugural = next(e for e in registry['editions'] if e['slug'] == 'simvltanea-inaugural')
assert inaugural['source']['folder'] == str(SAMPLES_DIR/'inaugural')
errors,_ = verify_editions.validate_payload(verify_editions.load_json(EDITIONS_FILE),SITE_DIR)
assert errors == [], errors
project = build_edition.load_json(EXAMPLES_DIR/'project.example.json')
assert project['input_dir'] == str(SAMPLES_DIR)
assert overnight_checkpoint.PACKAGE_ROOT == lane_ref('packages','triptych-video-canon-site')
SAMPLES_DIR.mkdir(parents=True)
sample=SAMPLES_DIR/'sample.txt'
sample.write_text('original source')
atom=atomize_media.atom_for_path(sample,chunk_bytes=1024,write_chunks=False,chunk_dir=WORK_DIR/'chunks',no_ffprobe=True)
assert atom.lane == 'samples'
report = generated_inventory.lane_report(next(lane for lane in generated_inventory.LANES if lane.path == 'samples'))
assert report.exists and report.files == 1
assert report.directory == lane_ref('samples')
assert structure.is_generated_path(sample.relative_to(REPO_ROOT).as_posix())
assert not subprocess.check_output(['git','-C',str(REPO_ROOT),'ls-files',str(sample)])
'''
            result = subprocess.run([sys.executable,'-c',program],cwd=root,env=env,
                                    capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_symlink_changes_cannot_escape_after_loading(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            manifest = self.alternate_manifest(root)
            layout = load_layout(root, manifest)
            samples = layout.path('samples')
            samples.parent.mkdir(parents=True)
            samples.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                layout.generated('samples', 'output.mp4')
            with self.assertRaises(ValueError):
                load_layout(root, manifest)

    def test_invalid_symbolic_references_are_rejected(self):
        for reference in ('@unknown/file', '@samples/../../outside', '@site/../private'):
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    resolve_references(reference)
        self.assertEqual(resolve_references('media/loop.mp4'), 'media/loop.mp4')

    def test_invalid_layouts_fail_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.alternate_manifest(root)
            original=manifest.read_text()
            for replacement in ('../outside','/tmp/absolute','local/cache','local/cache/intake'):
                with self.subTest(path=replacement):
                    manifest.write_text(original.replace('work = "local/cache/private/state"',f'work = "{replacement}"'))
                    with self.assertRaises(ValueError):
                        load_layout(root,manifest)
            self.assertFalse((root/'local').exists())


if __name__ == '__main__':
    unittest.main()
