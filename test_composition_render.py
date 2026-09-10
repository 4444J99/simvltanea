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

import composition as c
import render_triptych as r
from artifact001_layouts import build_artifact001
from make_artifact_001 import prepare, probe

HERE=Path(__file__).resolve().parent
ROOT=HERE/'artifact-001'

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
        for n in (3,4,5,6):
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
        with self.assertRaises(ValueError):build_artifact001(7)
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
        result=subprocess.run([sys.executable,str(HERE/'render_triptych.py'),'--state',str(ROOT/'state-3.json')],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0); self.assertIn('explicit --orientation',result.stderr)

    def test_original_command_graph_compatibility(self):
        original=ROOT/'baseline/render_triptych.original.py'
        if not original.exists():self.skipTest('original snapshot only included in execution bundle')
        spec=importlib.util.spec_from_file_location('triptych_baseline',original)
        old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
        old.SCRIPT_DIR=HERE
        for timing in ('clip','fixed'):
            for layout in ('story','left','middle','right'):
                for audio in ('none','panel','mix'):
                    for direction in ('forward','reverse','pingpong'):
                        argv=['render_triptych.py','--manifest',str(ROOT/'baseline-manifest.json'),
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
        command=[sys.executable,'render_triptych.py','--state',str(path),'--orientation','portrait',
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

if __name__=='__main__':unittest.main()
