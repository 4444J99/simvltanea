"""The measured tables of GRAVITY.md can be regenerated from this repository (DOC-9) and stay equal to the code."""
import copy
import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools.media import measure_gravity


class MeasuredTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measurer = measure_gravity.Measurer()
        cls.text = measure_gravity.DOC.read_text(encoding="utf-8")

    def test_the_page_equals_a_fresh_measurement(self):
        self.assertTrue(measure_gravity.render(self.text, self.measurer) == self.text,
                        "run python3 -m tools.media.measure_gravity --write")

    def test_check_mode_exits_zero_on_the_committed_page_and_one_on_a_wrong_number(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(measure_gravity.main(["--check"]), 0, out.getvalue())
        wrong = self.text.replace("| 5 | .492 / .377 |", "| 5 | .592 / .377 |")
        self.assertNotEqual(wrong, self.text)
        scratch = Path(tempfile.mkdtemp(prefix="measure-doc-"))
        self.addCleanup(shutil.rmtree, scratch, True)
        (scratch / "GRAVITY.md").write_text(wrong, encoding="utf-8")
        with mock.patch.object(measure_gravity, "DOC", scratch / "GRAVITY.md"), redirect_stdout(io.StringIO()):
            self.assertEqual(measure_gravity.main(["--check"]), 1)

    def test_two_measurements_are_identical(self):
        again = measure_gravity.Measurer()
        self.assertEqual(measure_gravity.by_loops_block(again), measure_gravity.by_loops_block(self.measurer))
        self.assertEqual(again.pool_digest, self.measurer.pool_digest)

    def test_the_pool_is_the_repositorys_own_synthetic_pool(self):
        self.assertEqual(len(self.measurer.pool), measure_gravity.POOL_SIZE)
        self.assertTrue(all("_truth" in record for record in self.measurer.pool))

    def test_a_preset_description_that_disagrees_with_the_measured_ratio_is_reported(self):
        self.assertEqual(measure_gravity.preset_claim_problems(self.measurer), [])
        table = copy.deepcopy(measure_gravity.PRESET_TABLE)
        table["sticky"]["description"] = "Gravity: about 2 times uniform at N=5."
        with mock.patch.object(measure_gravity, "PRESET_TABLE", table):
            problems = measure_gravity.preset_claim_problems(self.measurer)
        self.assertEqual(len(problems), 1)
        self.assertIn("sticky", problems[0])

    def test_opposites_only_biases_the_draw_and_does_not_pick_the_least_related_clip(self):
        """F7: the percentile of the pick under `opposites` is well above 0 and the least related candidate is rare."""
        stats = {label: measure_gravity.pick_ranks(self.measurer, config) for label, config in measure_gravity.OPPOSITE_SETTINGS}
        random_, sticky, opposites, strong, plain = (stats[label] for label, _ in measure_gravity.OPPOSITE_SETTINGS)
        self.assertAlmostEqual(random_[0], 0.5, delta=0.05)
        self.assertLess(opposites[0], random_[0] - 0.08)             # biased toward unlike clips ...
        self.assertGreater(opposites[0], 0.25)                       # ... but nowhere near the least related one
        self.assertLess(opposites[1], 0.10)                          # the least related candidate is rare
        self.assertGreater(sticky[0], 0.7)
        self.assertLess(plain[0], 0.05)                              # near-argmin needs the extreme settings
        self.assertGreater(plain[1], 0.5)
        self.assertLess(strong[0], opposites[0])

    def test_the_ratios_order_the_presets_and_gravity_beats_the_baseline_at_every_loop_count(self):
        ratios = measure_gravity.preset_ratios(self.measurer)
        self.assertLess(ratios["drift"], ratios["sticky"])
        self.assertLess(ratios["sticky"], ratios["magnetic"])
        for n in measure_gravity.LOOP_COUNTS:
            self.assertGreater(self.measurer.run(measure_gravity.DEFAULT, n)["same"],
                               self.measurer.run(measure_gravity.BASELINE, n)["same"])


if __name__ == "__main__":
    unittest.main()
