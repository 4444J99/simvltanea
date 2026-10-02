"""Architectural regressions for feature APIs."""
import unittest
from tools.verification.verify_feature_boundaries import violations, verify


class FeatureBoundaryTests(unittest.TestCase):
    def test_cross_feature_deep_imports_are_rejected(self):
        for source in ("from simvltanea.authoring.composition import StateError", "import simvltanea.browser.browser_runtime as runtime", "from ..rendering.render_triptych import Panel"):
            with self.subTest(source=source):
                self.assertTrue(violations(source, "generators"))

    def test_public_and_same_feature_imports_are_allowed(self):
        for source in ("from simvltanea.authoring import StateError", "from simvltanea.generators.make_audio_fixture import prepare", "from .make_audio_fixture import prepare"):
            self.assertEqual(violations(source, "generators"), [])

    def test_repository_respects_boundaries(self):
        self.assertEqual(verify(), [])

    def test_all_declared_exports_resolve(self):
        import importlib
        for name in ("authoring", "browser", "rendering", "generators"):
            feature = importlib.import_module("simvltanea." + name)
            if name == "generators":
                for export in feature.__all__:
                    importlib.import_module("simvltanea.generators." + export)
            for export in feature.__all__:
                with self.subTest(feature=name, export=export):
                    self.assertIsNotNone(getattr(feature, export))
            with self.assertRaises(AttributeError):
                getattr(feature, "missing_export")
