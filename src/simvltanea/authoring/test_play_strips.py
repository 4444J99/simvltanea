"""Play states on strips layouts (N up to 12): the layout_preset option, its refusals and the unchanged default."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from simvltanea.authoring import PlayError, composition, schedule_play
from simvltanea.authoring.test_gravity_pool import make_pool

# Computed from the code of origin/main (6535580) before layout_preset existed:
# schedule_play(make_pool(60), n, None, 30, fps=24, seed=7) -> sha256 of canonical_json(state).
BASELINE_DIGESTS = {
    3: "b85deb74ddb8a9c67ad71efc734155dae3ed7493913328ae0391c52f624ffc06",
    7: "f05de9cad3a9eeaf84040c2dab441770aca28a92ef417eb744c95fd31368a83f",
}


def digest(state) -> str:
    return hashlib.sha256(composition.canonical_json(state).encode("utf-8")).hexdigest()


class StripsPlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = make_pool(60)

    def play(self, n, **kwargs):
        return schedule_play(self.pool, n, None, 30, fps=24, seed=7, **kwargs)

    def test_default_call_is_unchanged_positive_control(self):
        for n, expected in BASELINE_DIGESTS.items():
            with self.subTest(n=n):
                self.assertEqual(digest(self.play(n)["state"]), expected)

    def test_n8_and_n12_are_valid_deterministic_and_have_events(self):
        for n in (8, 10, 12):
            with self.subTest(n=n):
                first = self.play(n, layout_preset="strips")
                composition.validate_state(first["state"])
                self.assertEqual(len(first["state"]["loops"]), n)
                self.assertTrue(first["state"]["events"])
                self.assertTrue(first["report"]["renderable"])
                again = self.play(n, layout_preset="strips")
                self.assertEqual(digest(first["state"]), digest(again["state"]))
                other = schedule_play(self.pool, n, None, 30, fps=24, seed=8, layout_preset="strips")
                self.assertNotEqual(digest(first["state"]), digest(other["state"]))

    def test_preset_object_is_accepted_like_its_name(self):
        from simvltanea.authoring.layout_presets import BUILTIN_PRESETS
        named = self.play(8, layout_preset="strips")
        given = self.play(8, layout_preset=dict(BUILTIN_PRESETS["strips"]))
        self.assertEqual(digest(named["state"]), digest(given["state"]))

    def test_counts_outside_the_supported_range_are_refused_clearly(self):
        with self.assertRaisesRegex(PlayError, r"strips preset 'strips' supports N=1\.\.12; count 13"):
            self.play(13, layout_preset="strips")
        for n in (1, 0, -3):
            with self.subTest(n=n), self.assertRaisesRegex(PlayError, "at least N = 2"):
                self.play(n, layout_preset="strips")

    def test_default_still_refuses_outside_2_to_7_and_unknown_presets_are_play_errors(self):
        for n in (1, 8, 12):
            with self.subTest(n=n), self.assertRaisesRegex(PlayError, r"N = 2\.\.7"):
                self.play(n)
        with self.assertRaisesRegex(PlayError, "unknown preset"):
            self.play(8, layout_preset="nope")
        with self.assertRaisesRegex(PlayError, "alternatives"):
            self.play(8, layout_preset="strips", base_state={})

    def test_adjacency_n12_is_symmetric_and_non_empty(self):
        adjacency = self.play(12, layout_preset="strips")["adjacency"]
        self.assertTrue(any(adjacency.values()))
        for (a, b), value in adjacency.items():
            self.assertEqual(value, adjacency[(b, a)])
        self.assertEqual(adjacency[("loop-1", "loop-2")], 1000)      # strips abut in both orientations
        self.assertEqual(adjacency[("loop-1", "loop-3")], 0)
        self.assertEqual(sum(1 for v in adjacency.values() if v) // 2, 11)

    def test_cli_flag_is_accepted_and_documented(self):
        from tools.media import play_state as cli
        from tools.media import test_play_state as tps
        self.assertIn("--layout-preset", cli.build_parser().format_help())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            root, out = tmp / "private", tmp / "state.json"
            tps.build_root(root, 60)
            code, stdout = tps.run("--root", root, "--out", out, "--n", "12", "--duration", "30", "--seed", "7",
                                   "--layout-preset", "strips")
            self.assertEqual(code, 0)
            state = composition.load_state(out)
            self.assertEqual(len(state["loops"]), 12)
            self.assertIn("state: n=12", stdout)
            code, _, stderr = tps.run_all("--root", root, "--out", out, "--force", "--n", "13", "--duration", "30",
                                          "--layout-preset", "strips")
            self.assertIn("N=1..12", str(code))
            code, _, _ = tps.run_all("--root", root, "--out", out, "--force", "--n", "9", "--duration", "30")
            self.assertIn("N = 2..7", str(code))


if __name__ == "__main__":
    unittest.main()
