"""Narrow executable acceptance suite. Prepare fixtures with make_artifact_001.py --prepare-only.

Media integration tests render small files through the same CLI; they are not
browser or historical-reconstruction tests. The original renderer snapshot in
the delivered bundle is optional for the stricter command-graph regression.
"""
from __future__ import annotations
import copy
import dataclasses
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

HERE = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
ROOT = HERE / 'var' / 'artifact-001'
BASELINE = HERE / 'fixtures' / 'artifact-001'

import simvltanea.authoring.composition as c
import simvltanea.rendering.render_triptych as r
from simvltanea.authoring.artifact001_layouts import build_artifact001
from simvltanea.authoring import build_strips, strips_layouts
from simvltanea.authoring.layout_presets import DEFAULT_STRIPS_PRESET
from simvltanea.generators.make_artifact_001 import prepare, probe
from simvltanea.generators.make_runtime_fixture import RAMP_SIZE, ramp_row, ramp_sources, ramp_tint

def get_state(n=3):
    return c.load_state(ROOT/f'state-{n}.json')

def loops(state, frame):
    return {x['id']:x for x in c.resolve_at(state,frame)['loops']}

class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepare(ROOT)

    def test_serialization_and_replay_round_trip(self):
        s=c.load_state(ROOT/'state-still-controls.json')
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            file=Path(directory)/'state.json'; c.save_state(s,file); again=c.load_state(file)
            self.assertEqual(s,again)
            for f in range(s['frames']):
                self.assertEqual(c.resolve_at(s,f),c.resolve_at(again,f))

    def test_randomness_evaluation_order_independent(self):
        s=get_state(); s['allow_source_reuse']=True
        for loop in s['loops']: loop['bank']=['media-1','media-2','media-3']
        other=copy.deepcopy(s); other['loops'].reverse()
        for frame in (0,1,23,24,48,71,72,143):
            self.assertEqual(loops(s,frame),loops(other,frame))

    def test_seed_changes_selection_not_clocks(self):
        s=get_state(); s['allow_source_reuse']=True
        for loop in s['loops']: loop['bank']=['media-1','media-2','media-3']
        patterns=[]
        for seed in range(8):
            changed=copy.deepcopy(s); changed['seed']=seed
            patterns.append(tuple(x['source'] for x in loops(changed,30).values()))
            self.assertEqual([x['local'] for x in loops(s,30).values()],
                             [x['local'] for x in loops(changed,30).values()])
        self.assertGreater(len(set(patterns)),1)

    def test_hold_release_no_catchup(self):
        s=get_state(); s['events']=[dict(op='hold',frame=24,loop='loop-1',value=True),
                                  dict(op='hold',frame=72,loop='loop-1',value=False)]
        self.assertEqual(loops(s,60)['loop-1']['local'],'1')
        self.assertEqual(loops(s,72)['loop-1']['local'],'1')
        self.assertEqual(loops(s,96)['loop-1']['local'],'2')
        self.assertEqual(loops(s,96)['loop-2'],loops(get_state(),96)['loop-2'])

    def test_reroll_target_only(self):
        s=get_state(); s['events']=[dict(op='reroll',frame=24,loop='loop-2')]
        before=loops(get_state(),25); after=loops(s,25)
        self.assertEqual(after['loop-2']['epoch'],1)
        self.assertEqual(after['loop-2']['local'],before['loop-2']['local'])
        self.assertEqual(after['loop-1'],before['loop-1'])

    def test_swap_sources_not_clocks(self):
        s=get_state(); s['events']=[dict(op='swap',frame=24,a='loop-1',b='loop-2')]
        for f in (24,60,120):
            original=loops(get_state(),f); actual=loops(s,f)
            self.assertEqual(actual['loop-1']['source'],original['loop-2']['source'])
            self.assertEqual(actual['loop-2']['source'],original['loop-1']['source'])
            self.assertEqual(actual['loop-1']['local'],original['loop-1']['local'])

    def test_move_changes_only_target_layout(self):
        s=get_state(); old=copy.deepcopy(s)
        s['events']=[dict(op='move',frame=24,loop='loop-1',orientation='portrait',
                          rect=['1/10','3/100','4/5','21/50'])]
        c.validate_state(s)
        self.assertEqual(loops(s,50),loops(old,50))
        self.assertEqual(c.resolve_at(s,50)['layouts']['landscape'],old['layouts']['landscape'])
        self.assertNotEqual(c.resolve_at(s,50)['layouts']['portrait'],old['layouts']['portrait'])

    def test_orientation_and_viewports_never_mutate_content(self):
        for n in (3,4,5,6,7):
            s=get_state(n); serial=c.canonical_json(s)
            for frame in (0,24,73,143):
                content=c.resolve_at(s,frame)['loops']
                for w,h in ((390,844),(844,390),(412,915),(915,412),(1366,768),(768,1366)):
                    actual=c.presentation_at(s,frame,w,h)
                    self.assertEqual(actual['loops'],content)
                    self.assertEqual(len(actual['layout']['cells']),n)
                    for p in c.pixel_placements(actual['layout'],w,h):
                        self.assertGreater(p.width*p.height,0)
                        self.assertLessEqual(p.x+p.width,w+1) # even-edge snap, no exporter odd sizes
                        self.assertLessEqual(p.y+p.height,h+1)
            self.assertEqual(c.canonical_json(s),serial)
        self.assertEqual(c.orientation_for(100,100),'landscape')

    def test_orientation_progression_not_frozen(self):
        s=get_state(6)
        observed=[c.presentation_at(s,f,w,h)['loops'] for f,w,h in
                  ((24,390,844),(48,844,390),(72,390,844))]
        self.assertEqual([x[0]['local'] for x in observed],['1','2','3'])

    def test_add_loop_preserves_existing_clocks(self):
        for f in (0,55,143):
            self.assertEqual(c.resolve_at(get_state(5),f)['loops'],c.resolve_at(get_state(6),f)['loops'][:5])

    def test_one_loop_per_cell_and_nonoverlap(self):
        for n in (3,4,5,6):
            s=get_state(n); c.validate_state(s)
            for layout in s['layouts'].values():
                self.assertEqual({p['loop'] for p in layout['cells']},{x['id'] for x in s['loops']})
                self.assertEqual(len(layout['cells']),n)

    def test_authoring_adapter_preserves_geometry_clocks(self):
        for n in (3,4,5,6):
            a=build_artifact001(n); s=get_state(n)
            for old,new in zip(a.loops,c.resolve_at(s,36)['loops']):
                self.assertAlmostEqual(old.media_time(1.5)%3,float(Fraction(new['source_offset'])),places=8)
            for orientation in c.ORIENTATIONS:
                for old,new in zip(a.layout(orientation).placements,s['layouts'][orientation]['cells']):
                    self.assertEqual([old.x,old.y,old.width,old.height],list(map(lambda x:float(Fraction(x)),new['rect'])))

    def test_authoring_adapter_rejects_untranslated_history(self):
        a=build_artifact001(3).apply(dict(type='hold',loop_id='loop-1'),1)
        with self.assertRaisesRegex(c.StateError,'initial snapshot'):
            c.from_authoring_model(a,{})

    def test_unknown_version_and_capabilities(self):
        for field,value in (('schema_version',2),('engine_version','99'),('rng','random'),
                            ('audio',dict(mode='mix',routing=None,generative=None))):
            s=get_state(); s[field]=value
            with self.assertRaises(c.StateError): c.validate_state(s)
        s=get_state();s['masks']={}
        with self.assertRaisesRegex(c.StateError,'unsupported fields'): c.validate_state(s)

    def test_invalid_numbers_and_banks(self):
        for key,value in (('rate',0),('rate','nan'),('rate',1.5),('offset',-1),('period',0),
                          ('bank',[]),('bank',['absent']),('bank',['media-1','media-1'])):
            s=get_state(); s['loops'][0][key]=value
            with self.assertRaises(c.StateError): c.validate_state(s)

    def test_missing_duplicate_and_hidden_layers_rejected(self):
        s=get_state();s['layouts']['portrait']['cells'].pop()
        with self.assertRaises(c.StateError):c.validate_state(s)
        s=get_state();s['layouts']['portrait']['cells'][1]['rect']=s['layouts']['portrait']['cells'][0]['rect']
        with self.assertRaisesRegex(c.StateError,'overlapping'):c.validate_state(s)
        s=get_state();s['loops'][0]['id']=s['loops'][1]['id']
        with self.assertRaises(c.StateError):c.validate_state(s)

    def test_event_failures(self):
        bad=[dict(op='unknown',frame=0),dict(op=[],frame=0),dict(op='hold',frame=0,loop=[],value=True),
             dict(op='hold',frame=0,loop='absent',value=True),dict(op='hold',frame=144,loop='loop-1',value=True),
             dict(op='swap',frame=0,a='loop-1',b='loop-1')]
        for event in bad:
            s=get_state();s['events']=[event]
            with self.assertRaises(c.StateError):c.validate_state(s)
        s=get_state();s['events']=[dict(op='reroll',frame=f,loop='loop-1') for f in (24,12)]
        with self.assertRaisesRegex(c.StateError,'ordered'):c.validate_state(s)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            p=Path(d)/'bad.json'; p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(c.StateError,'duplicate JSON key'):c.load_state(p)

    def test_missing_and_altered_media(self):
        s=get_state();s['sources'][0]['path']='absent.mp4'
        with self.assertRaisesRegex(c.StateError,'absent media'):c.media_paths(s,ROOT)
        s=get_state();s['sources'][0]['sha256']='0'*64
        with self.assertRaisesRegex(c.StateError,'hash mismatch'):c.media_paths(s,ROOT)

    def test_media_path_traversal_and_symlink(self):
        s=get_state();s['sources'][0]['path']='../outside.mp4'
        with self.assertRaises(c.StateError):c.validate_state(s)
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            p=Path(d)/'escape.mp4';p.symlink_to('/etc/hosts')
            s=get_state();s['sources'][0]['path']=str(p.relative_to(ROOT))
            with self.assertRaisesRegex(c.StateError,'escapes'):c.media_paths(s,ROOT)

    def test_implicit_source_reuse_rejected(self):
        s=get_state();s['loops'][1]['bank']=['media-1']
        with self.assertRaisesRegex(c.StateError,'reuse'):c.validate_state(s)
        s['allow_source_reuse']=True;c.validate_state(s)

    def test_trim_bounds_and_local_looping(self):
        s=get_state();s['loops'][0]['trim']=['1','2']
        c.validate_state(s)
        self.assertEqual(loops(s,24)['loop-1']['source_offset'],'1')
        s['loops'][0]['trim']=['1','4']
        with self.assertRaises(c.StateError):c.validate_state(s)

    def test_segment_compiler_reuses_existing_types(self):
        for n in (3,4,5,6):
            s=get_state(n)
            for orientation,w,h in (('portrait',360,640),('landscape',640,360)):
                segments=c.compile_segments(s,ROOT,orientation,w,h)
                self.assertTrue(all(isinstance(x,r.Segment) for x in segments))
                self.assertEqual(sum(round(x.duration*24) for x in segments),144)
                self.assertTrue(all(len(x.panels)==n and len(x.placements)==n for x in segments))

    def test_invalid_export_and_unsupported_count(self):
        with self.assertRaises(ValueError):build_artifact001(8)
        s=get_state()
        with self.assertRaisesRegex(c.StateError,'even'):c.compile_segments(s,ROOT,'portrait',361,640)
        with self.assertRaisesRegex(c.StateError,'orientation'):c.compile_segments(s,ROOT,'portrait',640,360)

    def test_baseline_schedule_semantics(self):
        clips=[r.Clip(0,Path('a.mp4'),1,True),r.Clip(1,Path('b.mp4'),2,False)]
        fixed=r.build_fixed_segments(clips,1)
        self.assertEqual(len(fixed),4)
        self.assertEqual(fixed[2].panels[2].source_offset,2)
        self.assertIsNone(fixed[-1].panels[0].source_path)
        timed=r.build_clip_segments(clips)
        self.assertEqual([x.duration for x in timed],[1,2,2,2])
        self.assertTrue(all(p.source_path is not None for p in timed[-1].panels))

    def test_legacy_defaults_and_invalid_state_cli(self):
        with patch.object(sys,'argv',['render_triptych.py']):
            settings=r.build_settings(r.parse_args())
        self.assertEqual((settings.width,settings.height,settings.fps),(1080,1920,30))
        self.assertEqual(settings.audio_mode,'none');self.assertEqual(settings.timing_mode,'clip')
        result=subprocess.run([sys.executable,str(HERE/'src'/'simvltanea'/'render_triptych.py'),'--state',str(ROOT/'state-3.json')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0); self.assertIn('explicit --orientation',result.stderr)

    def test_original_command_graph_compatibility(self):
        original=BASELINE/'baseline/render_triptych.original.py'
        if not original.exists():self.skipTest('original snapshot only included in execution bundle')
        spec=importlib.util.spec_from_file_location('triptych_baseline',original)
        old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
        old.SCRIPT_DIR=HERE
        for timing in ('clip','fixed'):
            for layout in ('story','left','middle','right'):
                for audio in ('none','panel','mix'):
                    for direction in ('forward','reverse','pingpong'):
                        argv=['render_triptych.py','--manifest',str(BASELINE/'baseline-manifest.json'),
                              '--timing',timing,'--phrase','1','--layout',layout,'--audio',audio,'--direction',direction,
                              '--panel-order','middle,left,right']
                        with patch.object(sys,'argv',argv):
                            a=old.build_settings(old.parse_args());b=r.build_settings(r.parse_args())
                        data=[old.Clip(i,ROOT/f'media/loop-{i+1}.mp4',1,True) for i in range(3)]
                        for segment in old.build_segments(data,a):
                            new=r.Segment(segment.index,segment.start,segment.duration,
                                          tuple(r.Panel(**dataclasses.asdict(p)) for p in segment.panels))
                            with patch.object(old,'run') as run_a,patch.object(r,'run') as run_b:
                                old.render_segment(Path('out.mp4'),segment,a);r.render_segment(Path('out.mp4'),new,b)
                            self.assertEqual(run_a.call_args,run_b.call_args)

class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):prepare(ROOT)

    def test_real_still_video_and_hold_render(self):
        s=c.load_state(ROOT/'state-still-controls.json')
        s['frames']=72;s['events']=[x for x in s['events'] if x['frame']<72]
        path=ROOT/'test-integration-state.json';c.save_state(s,path)
        output=ROOT/'renders/test-integration.mp4'
        command=[sys.executable,str(HERE/'src'/'simvltanea'/'render_triptych.py'),'--state',str(path),'--orientation','portrait',
                 '--width','360','--height','640','--preset','ultrafast','--output',str(output)]
        done=subprocess.run(command,cwd=HERE,capture_output=True,text=True)
        (ROOT/'evidence/integration.log').write_text(done.stdout+done.stderr)
        self.assertEqual(done.returncode,0,done.stderr)
        facts=probe(output);self.assertEqual(facts['streams'][0]['nb_frames'],'72')
        self.assertAlmostEqual(float(facts['format']['duration']),3)
        raw=subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        frame_bytes = 640 * 360 * 3
        cells=c.pixel_placements(s['layouts']['portrait'],360,640)
        def pixels(frame,cell):
            return b''.join(raw[frame*frame_bytes + (y*360+cell.x+4)*3:
                                frame*frame_bytes + (y*360+cell.x+cell.width-4)*3]
                            for y in range(cell.y+4,cell.y+cell.height-4))
        def difference(a,b):
            return sum(abs(x-y) for x,y in zip(a,b))/len(a)
        # Lossy H.264 may vary a few pixel values even for unchanged content.
        self.assertLess(difference(pixels(30,cells[0]),pixels(40,cells[0])),1)
        self.assertLess(difference(pixels(30,cells[1]),pixels(40,cells[1])),1)
        self.assertGreater(difference(pixels(30,cells[2]),pixels(40,cells[2])),2)
        self.assertGreater(difference(pixels(49,cells[1]),pixels(58,cells[1])),2)


# Filter-graph digests of states without the full-bleed keys, computed from the renderer
# and compiler at the commit before lane D (git archive of HEAD, same fixture states).
# A state without ``presentation`` must keep the historical graph byte for byte.
LEGACY_GRAPH_SHA256 = {
    'authored-2-contain-slice-seam/landscape': '7878396e0189796425225a89a64b00ea5277311a91268f4faceb168820db3383',
    'authored-2-contain-slice-seam/portrait': '7fe255a88830f93bcf2f6e1dc191378b06554e6cd2dfad036928841e277562f5',
    'authored-3/landscape': '0a47750f6efb1da98a91a9c47a1762ca2c086825d5bfb6dccf3bc1871635c186',
    'authored-3/portrait': 'e040414a509990a5759fa9082a664b60853ce0f3eee0f5a11ddadd9b752b3887',
    'authored-5-slice/landscape': 'c683f9785ca5fe4953795442faec882be7758aa096aa95939b671cd79d580d43',
    'authored-5-slice/portrait': 'ea0f81e19054ad4d3a64d65830de9f109ffcec43046f6415ba73bde48b8a09dc',
    'rows-5-no-new-keys/landscape': 'bfc769ab137338b1135209905a0242909995827f21c7bcf50644f55ca677e81f',
    'rows-5-no-new-keys/portrait': 'c9d4e6e02ef38b10e4494bdebf1a2780a6d0a1127646baa96732a764cf3c22c7',
    'still-controls/landscape': '52741809eae016bbee2f300290ff7fff41d5c27fc563ab41c269b6f178dc280f',
    'still-controls/portrait': '88d2b86b26d68b0750bf5c6b74b0e78cd26d9e693fef1f8e8f50d606020d6551',
}


def legacy_states():
    s3 = get_state(3)
    s5 = get_state(5); s5['slice'] = {'enabled': True, 'width': '1/2', 'height': '1/2'}
    s2 = get_state(2)
    for layout in s2['layouts'].values():
        for cell in layout['cells']: cell['fit'] = 'contain'
    s2['slice'] = {'enabled': True, 'width': '1/2', 'height': '33/50'}
    s2['seam'] = {'enabled': True, 'width': '9/250', 'mode': 'feather', 'sigma': '1/200'}
    rows = get_state(5)
    rows['layouts'] = {o: {'name': f'rows-{o}', 'cells': [
        dict(loop=f'loop-{k+1}', rect=(['0', f'{k}/5', '1', '1/5'] if o == 'portrait' else [f'{k}/5', '0', '1/5', '1']),
             fit='cover', focal=['1/2', '1/2']) for k in range(5)]} for o in ('portrait', 'landscape')}
    rows['slice'] = {'enabled': True, 'width': '41/125', 'height': '41/125'}
    still = c.load_state(ROOT/'state-still-controls.json')
    return {'authored-3': s3, 'authored-5-slice': s5, 'authored-2-contain-slice-seam': s2,
            'rows-5-no-new-keys': rows, 'still-controls': still}


def segment_graphs(state, orientation, width, height, root=ROOT):
    with patch.object(sys, 'argv', ['render_triptych.py']):
        settings = r.build_settings(r.parse_args())
    settings = dataclasses.replace(settings, width=width, height=height, fps=state['fps'])
    graphs = []
    for segment in c.compile_segments(state, root, orientation, width, height):
        with patch.object(r, 'run') as run:
            r.render_segment(Path('segment.mp4'), segment, settings)
        command = run.call_args[0][0]
        graphs.append(command[command.index('-filter_complex') + 1])
    return graphs


class StripsRenderTests(unittest.TestCase):
    """Full-bleed strips in the FFmpeg export: hidden bleed, corner mask, jitter overscan.

    Clips are the runtime-fixture ramps: red encodes the source row, blue the clip.
    No ramp pixel is near black, so a near-black export pixel is exposed background.
    """

    @classmethod
    def setUpClass(cls):
        prepare(ROOT)
        cls.ramps = ramp_sources(ROOT)

    def strips(self, count, overlap=None, radius=None, jitter=None, offsets=None, zoom=True, frames=6, preset='strips'):
        state = build_strips(count, preset, sources=self.ramps[:count], frames=frames)
        for layout in state['layouts'].values():
            presentation = layout['presentation']
            if overlap is not None:
                presentation['overlap_px'] = overlap
            if radius is not None:
                presentation['corner_radius'] = radius
            if jitter is not None:
                presentation['lateral_jitter'] = jitter
                for index, cell in enumerate(layout['cells']):
                    cell['lateral_offset'] = offsets[index % len(offsets)]
        if not zoom:
            del state['slice']
        c.validate_state(state)
        return state

    def render(self, state, name, orientation, width, height, crf=None):
        path = ROOT/f'test-{name}.json'; c.save_state(state, path)
        output = ROOT/'renders'/f'test-{name}-{orientation}.mp4'
        command = [sys.executable, '-m', 'simvltanea.rendering.render_triptych', '--state', str(path),
                   '--orientation', orientation, '--width', str(width), '--height', str(height),
                   '--preset', 'ultrafast', '--output', str(output)] + (['--crf', str(crf)] if crf is not None else [])
        done = subprocess.run(command, cwd=HERE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-4000:])
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, check=True).stdout
        frame = width * height * 3
        self.assertEqual(len(raw), frame * state['frames'])
        self.output = output
        return [raw[i:i + frame] for i in range(0, len(raw), frame)]

    def colour(self, width, height, index):
        """Frame ``index`` of the last render as an exact BT.601 ``(x, y) -> (r, g, b)`` reader.

        Measurements decode to yuv444p and convert here, so no FFmpeg RGB fast path
        (FFmpeg 9 biases red by about 2 levels from yuv420p) moves a ramp reading.
        """
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.output), '-vf', f'select=eq(n\\,{index})',
                              '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'yuv444p', '-'],
                             capture_output=True, check=True).stdout
        plane = width * height
        self.assertEqual(len(raw), 3 * plane)
        def read(x, y):
            i = y * width + x
            luma, cb, cr = 1.164 * (raw[i] - 16), raw[plane + i] - 128, raw[2 * plane + i] - 128
            return luma + 1.596 * cr, luma - 0.392 * cb - 0.813 * cr, luma + 2.017 * cb
        return read

    @staticmethod
    def row_mean(read, x0, x1, y, channel):
        return sum(read(x, y)[channel] for x in range(x0, x1)) / (x1 - x0)

    @staticmethod
    def background(frame):
        return sum(1 for i in range(0, len(frame), 3) if max(frame[i], frame[i + 1], frame[i + 2]) < 40)

    def blue_floor(self, width, height, index=0):
        """Lowest BT.601 blue of frame ``index`` of the last render, per 2x2 chroma block.

        Every ramp tint is at least 80, so a reading below 72 means a block took at least
        a tenth of the black background. Each block pairs its mean luma with its own chroma
        sample: at a rounded corner two strips share a block, and a per-pixel reading would
        pair one strip's luma with the shared chroma (tens of levels off) without any
        background showing. Renders measured here use CRF 12, which keeps x264 noise on the
        sharp arc edges a few levels clear of the floor.
        """
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(self.output), '-vf', f'select=eq(n\\,{index})',
                              '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-'],
                             capture_output=True, check=True).stdout
        plane, half = width * height, width // 2
        self.assertEqual(len(raw), plane * 3 // 2)
        def blue(bx, by):
            i = 2 * by * width + 2 * bx
            luma = (raw[i] + raw[i + 1] + raw[i + width] + raw[i + width + 1]) / 4
            return 1.164 * (luma - 16) + 2.017 * (raw[plane + by * half + bx] - 128)
        return min(blue(bx, by) for by in range(height // 2) for bx in range(half))

    @staticmethod
    def preset(**changes):
        preset = copy.deepcopy(DEFAULT_STRIPS_PRESET)
        preset['name'] = 'strips-test'
        if 'order' in changes:
            for orientation in preset['orientations'].values():
                orientation['order'] = changes['order']
        if 'weights' in changes:
            preset['weights']['by_count'] = {str(len(changes['weights'])): changes['weights']}
        return preset


    def test_legacy_filter_graphs_are_unchanged(self):
        for name, state in legacy_states().items():
            for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
                cells = c.pixel_placements(state['layouts'][orientation], width, height)
                self.assertTrue(all(cell.raster is None for cell in cells))
                digest = hashlib.sha256('\n'.join(segment_graphs(state, orientation, width, height)).encode()).hexdigest()
                self.assertEqual(digest, LEGACY_GRAPH_SHA256[f'{name}/{orientation}'], f'{name}/{orientation}')

    def test_presentation_pixel_geometry(self):
        width, height = 360, 780
        layout = strips_layouts(5)['portrait']
        cells = c.pixel_placements(layout, width, height)
        self.assertEqual([(p.x, p.y, p.width, p.height) for p in cells],
                         [(0, 0, 360, 156), (0, 156, 360, 156), (0, 312, 360, 156), (0, 468, 360, 156), (0, 624, 360, 156)])
        self.assertEqual([p.raster.bleed for p in cells], [(0, 0, 0, 2)] * 4 + [(0, 0, 0, 0)])
        self.assertEqual([p.drawn_box() for p in cells][0], (0, 0, 360, 158))
        for k in (1, 3, 5, 8):  # 2*ceil(k/2)
            layout['presentation']['overlap_px'] = k
            self.assertEqual(c.pixel_placements(layout, width, height)[0].raster.bleed[3], 2 * -(-k // 2))
        # Rounded corners: only the sides shared with an earlier strip; bleed grows by ceil(radius).
        layout['presentation'].update(overlap_px=2, corner_radius='1/20')
        cells = c.pixel_placements(layout, width, height)
        self.assertEqual(cells[0].raster.corners, ())
        self.assertTrue(all(p.raster.corners == ('top-left', 'top-right') and p.raster.radius == 18 for p in cells[1:]))
        self.assertEqual([p.raster.bleed[3] for p in cells], [20, 20, 20, 20, 0])
        # Bleed is clamped to half the later neighbour (even): N=12 at 360x360 strips are 30 px.
        tiny = strips_layouts(12)['landscape']; tiny['presentation']['corner_radius'] = '1/20'
        self.assertEqual({p.raster.bleed[2] for p in c.pixel_placements(tiny, 360, 360)[:-1]}, {14})
        # Reverse draw order: strips listed bottom to top bleed upward.
        reverse = strips_layouts(5)['portrait']; reverse['cells'].reverse()
        self.assertEqual([p.raster.bleed for p in c.pixel_placements(reverse, width, height)],
                         [(0, 2, 0, 0)] * 4 + [(0, 0, 0, 0)])
        # A side only partly under later cells never grows (the bleed would be visible).
        partial = {'name': 'partial', 'presentation': {'overlap_px': 2, 'corner_radius': '0', 'lateral_jitter': '0'},
                   'cells': [dict(loop='a', rect=['0', '0', '1', '1/2'], fit='cover', focal=['1/2', '1/2']),
                             dict(loop='b', rect=['0', '1/2', '1/2', '1/2'], fit='cover', focal=['1/2', '1/2'])]}
        self.assertEqual(c.pixel_placements(partial, width, height)[0].raster.bleed, (0, 0, 0, 0))
        # Lateral jitter: overscan 2*ceil(J*L/2) along the strip, offset rounded to even.
        jittered = strips_layouts(5)['landscape']
        jittered['presentation']['lateral_jitter'] = '1/20'
        for cell, offset in zip(jittered['cells'], ('1/20', '-1/20', '0', '1/40', '-3/200')):
            cell['lateral_offset'] = offset
        cells = c.pixel_placements(jittered, 640, 360)
        self.assertEqual([p.raster.overscan for p in cells], [(0, 18)] * 5)
        self.assertEqual([p.raster.shift for p in cells], [(0, 18), (0, -18), (0, 0), (0, 10), (0, -6)])
        rows = strips_layouts(5)['portrait']; rows['presentation']['lateral_jitter'] = '1/40'
        for cell in rows['cells']: cell['lateral_offset'] = '1/40'
        self.assertEqual({(p.raster.overscan, p.raster.shift) for p in c.pixel_placements(rows, width, height)},
                         {((10, 0), (10, 0))})
        single = strips_layouts(1)
        self.assertEqual(c.pixel_placements(single['portrait'], width, height)[0].raster, r.Raster())

    def test_bleed_is_hidden_and_never_changes_a_visible_pixel(self):
        for count in (1, 5, 8, 12):
            for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
                with self.subTest(count=count, orientation=orientation):
                    plain = self.render(self.strips(count, overlap=0), f'bleed-{count}-0', orientation, width, height)
                    for overlap in ((2, 8) if count > 1 else ()):
                        state = self.strips(count, overlap=overlap)
                        graphs = segment_graphs(state, orientation, width, height)
                        self.assertTrue(all(f'pad=w=iw+{2 * -(-overlap // 2)}' in g or f'h=ih+{2 * -(-overlap // 2)}' in g
                                            for g in graphs))
                        bled = self.render(state, f'bleed-{count}-{overlap}', orientation, width, height)
                        self.assertEqual(bled, plain, f'overlap_px {overlap} changed a visible pixel')
                    self.assertEqual([self.background(f) for f in plain], [0] * len(plain))

    def test_style_maxima_never_expose_background(self):
        offsets = ('1/20', '-1/20', '0', '1/40', '-1/40')
        for count in (1, 5, 8, 12):
            for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360), ('landscape', 360, 360)):
                with self.subTest(count=count, orientation=orientation, size=(width, height)):
                    state = self.strips(count, overlap=8 if count > 1 else 0,
                                        radius='1/20' if count > 1 else None, jitter='1/20', offsets=offsets)
                    frames = self.render(state, f'styled-{count}', orientation, width, height, crf=12)
                    self.assertEqual([self.background(f) for f in frames], [0] * len(frames))
                    self.assertGreaterEqual(self.blue_floor(width, height), 72)
                    # A renderer that ignored presentation would also have no background pixel: the styled
                    # frame must differ from the same state drawn with no bleed, radius or jitter.
                    plain = self.render(self.strips(count, overlap=0), f'styled-plain-{count}', orientation, width, height)
                    self.assertNotEqual(frames[0], plain[0], 'the export ignored the presentation styles')

    def test_rounded_corners_show_the_earlier_strip_only_in_the_corner(self):
        state = self.strips(5, radius='1/20')
        for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
            frame = self.render(state, 'corners-5', orientation, width, height)[2]
            read = self.colour(width, height, 2)
            cells = c.pixel_placements(state['layouts'][orientation], width, height)
            for k in range(1, 5):
                cell = cells[k]
                # Radius 18 px: (3, 3) from the corner is outside the arc, (3, 30) is past it.
                if orientation == 'portrait':
                    corner, mid, beyond = (3, cell.y + 3), (width // 2, cell.y + 3), (3, cell.y + 30)
                else:
                    corner, mid, beyond = (cell.x + 3, 3), (cell.x + 3, height // 2), (cell.x + 30, 3)
                tint = lambda point: read(*point)[2]
                # Neighbouring tints differ by 14: within half of that names the clip unambiguously.
                self.assertLess(abs(tint(corner) - ramp_tint(k - 1)), 7, (orientation, k, 'corner', tint(corner)))
                self.assertLess(abs(tint(mid) - ramp_tint(k)), 7, (orientation, k, 'edge', tint(mid)))
                self.assertLess(abs(tint(beyond) - ramp_tint(k)), 7, (orientation, k, 'past the radius'))
            self.assertEqual(self.background(frame), 0)

    def test_thin_strips_round_only_as_far_as_their_backing(self):
        # A strip thinner than 2*(overlap_px + radius) caps the earlier strip's bleed below
        # overlap_px + radius; its radius shrinks to fit, so no cutout reaches the background.
        cases = ((12, 'strips', 'landscape', 360, 360), (11, 'strips', 'landscape', 360, 360),
                 (12, 'strips', 'landscape', 1080, 1080), (2, self.preset(weights=['99', '1']), 'portrait', 900, 1000))
        for count, preset, orientation, width, height in cases:
            with self.subTest(count=count, size=(width, height)):
                state = self.strips(count, radius='1/20', frames=2, preset=preset)
                cells = c.pixel_placements(state['layouts'][orientation], width, height)
                for before, cell in zip(cells, cells[1:]):
                    self.assertGreater(cell.raster.radius, 0)
                    self.assertLessEqual(cell.raster.radius + 2, max(before.raster.bleed))
                styled = self.render(state, f'thin-{count}-{width}', orientation, width, height, crf=12)[0]
                self.assertEqual(self.background(styled), 0)
                self.assertGreaterEqual(self.blue_floor(width, height), 72)
                plain = self.render(self.strips(count, radius='0', frames=2, preset=preset),
                                    f'thin-{count}-{width}-square', orientation, width, height)[0]
                self.assertNotEqual(styled, plain, 'the export ignored corner_radius')

    def test_reverse_order_hides_the_bleed_and_rounds_the_far_corners(self):
        reverse = self.preset(order='reverse')
        for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
            with self.subTest(orientation=orientation):
                plain = [self.render(self.strips(5, overlap=k, frames=2, preset=reverse), f'reverse-{k}',
                                     orientation, width, height) for k in (0, 2, 8)]
                self.assertEqual(plain[1], plain[0], 'overlap_px 2 changed a visible pixel')
                self.assertEqual(plain[2], plain[0], 'overlap_px 8 changed a visible pixel')
                state = self.strips(5, radius='1/20', frames=2, preset=reverse)
                styled = self.render(state, 'reverse-corners', orientation, width, height, crf=12)
                self.assertEqual(self.background(styled[0]), 0)
                self.assertGreaterEqual(self.blue_floor(width, height), 72)
                self.assertNotEqual(styled[0], plain[1][0])
                read = self.colour(width, height, 0)
                cells = c.pixel_placements(state['layouts'][orientation], width, height)
                for k in range(1, 5):
                    cell = cells[k]
                    # Cell k draws clip 4-k over clip 5-k. 3 px inside its far corner (radius 18 px)
                    # the earlier strip shows; at radius 0 that pixel is clip 4-k.
                    if orientation == 'portrait':
                        self.assertEqual(cell.raster.corners, ('bottom-left', 'bottom-right'))
                        corner = (width - 4, cell.y + cell.height - 4)
                    else:
                        self.assertEqual(cell.raster.corners, ('top-right', 'bottom-right'))
                        corner = (cell.x + cell.width - 4, height - 4)
                    tint = read(*corner)[2]
                    self.assertLess(abs(tint - ramp_tint(5 - k)), 7, (orientation, k, tint))

    def test_a_corner_without_backing_stays_square(self):
        # A valid 2x2 grid drawn bottom-right, top-left, top-right, bottom-left. The top-left
        # cell's right bleed would leave its bottom-right corner square uncovered, so it is
        # dropped; the top-right cell, whose top-left corner only that bleed backs, stays square.
        state = self.strips(4, radius='1/20', frames=2)
        rects = (['1/2', '1/2', '1/2', '1/2'], ['0', '0', '1/2', '1/2'], ['1/2', '0', '1/2', '1/2'], ['0', '1/2', '1/2', '1/2'])
        for layout in state['layouts'].values():
            for cell, rect in zip(layout['cells'], rects):
                cell['rect'] = rect
        c.validate_state(state)
        for orientation, width, height in (('portrait', 360, 640), ('landscape', 640, 360)):
            with self.subTest(orientation=orientation):
                cells = c.pixel_placements(state['layouts'][orientation], width, height)
                self.assertEqual(cells[1].raster.bleed, (0, 0, 0, 20))
                self.assertEqual((cells[2].raster.radius, cells[2].raster.corners), (0.0, ()))
                self.assertEqual(cells[3].raster.corners, ('top-left', 'top-right', 'bottom-right'))
                frame = self.render(state, 'grid-4', orientation, width, height, crf=12)[0]
                self.assertEqual(self.background(frame), 0)
                self.assertGreaterEqual(self.blue_floor(width, height), 72)

    def test_lateral_jitter_slides_the_picture_by_the_resolved_offset(self):
        # Columns slide along y. Without zoom, cover fits the 540x720 clip to the cell
        # overscanned by J*H on both ends, so canvas row y shows source row
        # (y + J*H - offset*H) * 720 / (H + 2*J*H), within the spec's 2% parity tolerance.
        offsets = ('1/20', '-1/20', '0', '1/40', '-1/40')
        width, height = 640, 360
        state = self.strips(5, jitter='1/20', offsets=offsets, zoom=False)
        self.render(state, 'jitter-5', 'landscape', width, height)
        read = self.colour(width, height, 2)
        source_h = RAMP_SIZE[1]
        margin = height / 20
        for k, offset in enumerate(offsets):
            x0 = k * 128
            for y in (40, 180, 320):
                red = self.row_mean(read, x0 + 8, x0 + 120, y, 0)
                expected = (y + 0.5 + margin - float(Fraction(offset)) * height) * source_h / (height + 2 * margin) - 0.5
                self.assertLess(abs(ramp_row(red) - expected), 0.02 * source_h, (k, y, red, expected))

    def test_strips_export_crops_then_covers_each_strip(self):
        # Export half of spec seam test 7: each strip shows the source rows predicted by
        # crop (slice window) then cover, not the whole window stretched to the strip.
        width, height = 360, 780
        state = self.strips(5, frames=2)
        self.render(state, 'rows-5', 'portrait', width, height)
        read = self.colour(width, height, 0)
        snapshot = c.resolve_at(state, 0)
        source_w, source_h = RAMP_SIZE
        for k, (loop, cell) in enumerate(zip(snapshot['loops'], c.pixel_placements(state['layouts']['portrait'], width, height))):
            sx, sy, sw, sh = (float(Fraction(v)) for v in loop['slice_rect'])
            window_w, window_h = source_w * sw, source_h * sh
            scale = max(cell.width / window_w, cell.height / window_h)
            spare = window_h * scale - cell.height
            for y in (cell.y + 2, cell.y + cell.height - 3):
                expected = sy * source_h + ((y - cell.y) + 0.5 + spare / 2) / scale - 0.5
                red = self.row_mean(read, 8, width - 8, y, 0)
                self.assertLess(abs(ramp_row(red) - expected), 0.02 * source_h, (k, y, red, expected))

    def test_segment_cap_error_names_the_cap_and_the_remedy(self):
        state = build_strips(12, sources=self.ramps, frames=2400)
        for loop in state['loops']:
            loop['trim'] = ['0', '1/4']
        c.validate_state(state)
        with self.assertRaises(c.StateError) as caught:
            c.compile_segments(state, ROOT, 'portrait', 360, 640, verify_media=False)
        message = str(caught.exception)
        self.assertIn(f"cap of {c.MAX_SEGMENTS} segments (MAX_SEGMENTS)", message)
        self.assertRegex(message, r'needs \d+ render segments')
        self.assertIn('Remedy: shorten the export to at most', message)
        self.assertIn('No panels were removed', message)
        fits = int(message.split('at most ')[1].split(' frames')[0])
        state['frames'] = fits
        self.assertEqual(len(c.compile_segments(state, ROOT, 'portrait', 360, 640, verify_media=False)), c.MAX_SEGMENTS)


if __name__=='__main__':unittest.main()
