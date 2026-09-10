"""Reject malformed authoring snapshots before conversion to the strict compiler."""
from dataclasses import replace
import math
import unittest
from artifact001_layouts import build_artifact001


class AuthoringContractTests(unittest.TestCase):
    def test_invalid_loop_numbers(self):
        base = build_artifact001(3)
        for field, value in (("rate", 0), ("rate", -1), ("rate", math.nan),
                             ("offset", math.inf), ("trim_in", -1),
                             ("trim_out", 0), ("held_at", math.nan)):
            with self.subTest(field=field, value=value):
                bad = replace(base, loops=(replace(base.loops[0], **{field: value}),) + base.loops[1:])
                with self.assertRaises(ValueError):
                    bad.validate()

    def test_missing_source_and_empty_identity(self):
        base = build_artifact001(3)
        for field in ("source", "id"):
            bad = replace(base, loops=(replace(base.loops[0], **{field: ""}),) + base.loops[1:])
            with self.assertRaises(ValueError):
                bad.validate()

    def test_empty_composition(self):
        base = build_artifact001(3)
        bad = replace(base, loops=(), layouts=tuple(replace(l, placements=()) for l in base.layouts))
        with self.assertRaises(ValueError):
            bad.validate()

    def test_duplicate_orientation(self):
        base = build_artifact001(3)
        with self.assertRaises(ValueError):
            replace(base, layouts=base.layouts + (base.layouts[0],)).validate()

    def test_unknown_engine(self):
        with self.assertRaises(ValueError):
            replace(build_artifact001(3), engine_version="unknown").validate()

    def test_advancing_orientation_preserves_every_loop(self):
        base = build_artifact001(6)
        states = []
        for clock, orientation in ((1, "portrait"), (2, "landscape"), (3, "portrait")):
            self.assertEqual({p.loop_id for p in base.layout(orientation).placements}, set(base.loop_ids))
            states.append({l.id: (l.source, l.media_time(clock)) for l in base.loops})
        for loop in base.loops:
            for a, b in zip(states, states[1:]):
                self.assertEqual(a[loop.id][0], b[loop.id][0])
                self.assertAlmostEqual(b[loop.id][1] - a[loop.id][1], loop.rate)



class BindingContractTests(unittest.TestCase):
    @staticmethod
    def state():
        import composition as c
        import hashlib
        # Schema-only bindings: these are not claims of playable media bytes.
        sources = {f'fixtures/loop-{i}.mp4': dict(id=f'media-{i}',path=f'media/loop-{i}.mp4',
                   sha256=hashlib.sha256(f'schema-fixture-{i}'.encode()).hexdigest(),
                   kind='video',duration='3') for i in range(1,4)}
        return c.from_authoring_model(build_artifact001(3),sources)

    def test_duplicate_bytes_need_explicit_reuse_even_with_distinct_ids(self):
        import composition as c
        state = self.state()
        state['sources'][1]['sha256'] = state['sources'][0]['sha256']
        with self.assertRaisesRegex(c.StateError, 'reuse'):
            c.validate_state(state)
        state['allow_source_reuse'] = True
        c.validate_state(state)

    def test_authored_z_order_reaches_compiled_placements(self):
        import composition as c
        base = build_artifact001(3)
        layouts = tuple(replace(l, placements=tuple(replace(p,z=z) for p,z in zip(l.placements,(3,-1,1))))
                        for l in base.layouts)
        authored = replace(base, layouts=layouts)
        current = self.state()
        mapping = {f'fixtures/loop-{i+1}.mp4': src for i,src in enumerate(current['sources'])}
        state = c.from_authoring_model(authored,mapping)
        for orientation in c.ORIENTATIONS:
            self.assertEqual([p.name for p in c.pixel_placements(state['layouts'][orientation],360,640)],
                             ['loop-2','loop-3','loop-1'])
        self.assertEqual(c.resolve_at(state,24)['loops'],c.resolve_at(c.from_authoring_model(base,mapping),24)['loops'])


if __name__ == "__main__":
    unittest.main()
