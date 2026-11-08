"""Effects Lab delivery, privacy, and selected-layer interaction contracts."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from .browser_lab import LAB_FILES, LAB_HTML, lab_files

MODULE = Path(__file__).with_name('browser.lab_ui.js')


class ShellParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class EffectsLabShellTests(unittest.TestCase):
    def setUp(self):
        self.shell = ShellParser()
        self.shell.feed(LAB_HTML)

    def test_delivery_has_only_expected_assets_and_ordered_dependencies(self):
        files = lab_files()
        self.assertEqual(set(files), set(LAB_FILES))
        self.assertTrue(all(isinstance(value, bytes) and value for value in files.values()))
        scripts = [attrs for tag, attrs in self.shell.elements if tag == 'script']
        self.assertEqual([s['src'] for s in scripts],
                         ['lab_model.js', 'lab_audio.js', 'lab_engine.js', 'lab_ui.js'])
        self.assertTrue(all('defer' in s for s in scripts))
        self.assertEqual(len({a['id'] for _, a in self.shell.elements if 'id' in a}),
                         len([a for _, a in self.shell.elements if 'id' in a]))

    def test_media_remains_local_and_no_inline_event_handlers(self):
        policies = [a['content'] for tag, a in self.shell.elements
                    if tag == 'meta' and a.get('http-equiv') == 'Content-Security-Policy']
        self.assertEqual(len(policies), 1)
        policy = policies[0]
        for directive in ["default-src 'none'", "script-src 'self'", "connect-src 'none'",
                          'media-src blob:', "base-uri 'none'", "form-action 'none'"]:
            self.assertIn(directive, policy)
        for _, attrs in self.shell.elements:
            self.assertFalse(any(key.startswith('on') for key in attrs))
            for attr in ('src', 'href'):
                if attr in attrs:
                    self.assertNotRegex(attrs[attr], r'^(?:https?:)?//')
        media = next(a for _, a in self.shell.elements if a.get('id') == 'media-input')
        self.assertIn('audio/*', media['accept'])
        self.assertIn('video/*', media['accept'])
        self.assertIn('.mov', media['accept'])

    def test_public_workspace_is_empty_and_only_offers_local_media(self):
        by_id = {a['id']: (tag, a) for tag, a in self.shell.elements if 'id' in a}
        self.assertIn('preview-empty', by_id)
        self.assertIn('timeline-empty', by_id)
        self.assertIn('timeline-import', by_id)
        self.assertIn('bin-import', by_id)
        self.assertNotIn('source-dialog', by_id)
        self.assertFalse(any('data-demo' in attrs for _, attrs in self.shell.elements))
        self.assertIn('00 clips / 08 slots', LAB_HTML)
        self.assertIn('your footage or found sounds', LAB_HTML)
        self.assertNotIn('Generated sources</h2>', LAB_HTML)
        self.assertFalse(any(tag == 'img' for tag, _ in self.shell.elements))

    def test_initial_gesture_and_accessible_tab_contract(self):
        by_id = {a['id']: (tag, a) for tag, a in self.shell.elements if 'id' in a}
        self.assertEqual(by_id['transport-play'][0], 'button')
        self.assertEqual(by_id['lab-status'][1]['aria-live'], 'polite')
        for name in ['picture', 'sound', 'motion']:
            tab = by_id['tab-' + name][1]
            panel = by_id[tab['aria-controls']][1]
            self.assertEqual(tab['role'], 'tab')
            self.assertEqual(panel['role'], 'tabpanel')
            self.assertEqual(panel['aria-labelledby'], 'tab-' + name)
        self.assertIn('isolation:isolate', LAB_HTML)
        self.assertIn('grid-template-columns:minmax(0,1fr)', LAB_HTML)
        for name in ['timeline-scroll', 'timeline-ruler', 'timeline-tracks', 'transport-stop', 'loop-start', 'loop-end', 'media-drop']:
            self.assertIn(name, by_id)
        self.assertNotIn('welcome', by_id)
        for name in ['arrange', 'perform']:
            self.assertEqual(by_id['view-' + name][1]['aria-controls'], name + '-panel')


@unittest.skipUnless(shutil.which('node'), 'Node.js is required')
class EffectsLabUIContractTests(unittest.TestCase):
    def evaluate(self, expression):
        script = f"const ui=require({json.dumps(str(MODULE))}); const m=global.SimvltaneaLabModel; console.log(JSON.stringify({expression}));"
        result = subprocess.run(['node', '-e', script], check=True, text=True, capture_output=True)
        return json.loads(result.stdout)

    def test_a_setting_edit_targets_one_voice_and_one_key(self):
        value = self.evaluate("""(()=>{
          const settings={a:m.normalizeSettings({audioRate:1.7}),b:m.normalizeSettings({audioRate:.6})};
          const calls=[]; const engine={set:(id,patch)=>{calls.push([id,patch]); settings[id]=m.normalizeSettings(patch,settings[id]);}};
          ui.selectedPatch(engine,'b','combMix',.9);
          ui.selectedPatch(engine,null,'audioGain',0);
          ui.selectedPatch(engine,'a','url','blob:secret');
          return {calls,settings};
        })()""")
        self.assertEqual(value['calls'], [['b', {'combMix': .9}]])
        self.assertEqual(value['settings']['a']['combMix'], .45)
        self.assertEqual(value['settings']['b']['combMix'], .9)
        self.assertEqual(value['settings']['a']['audioRate'], 1.7)
        self.assertEqual(value['settings']['b']['audioRate'], .6)

    def test_session_round_trip_keeps_order_and_settings_without_media(self):
        value = self.evaluate("""(()=>{
          const snapshot={volume:.37,muted:true,sequence:{enabled:true,interval:11},clips:[
            {id:'a',name:'Tide',kind:'demo',settings:m.normalizeSettings({blend:'difference',combMix:.8})},
            {id:'b',name:'my film.mov',kind:'video',url:'blob:private',bytes:'private bytes',settings:{audioLife:90,videoLife:8,url:'blob:private'}}]};
          const sources=new Map([['a',{demo:'tide'}],['b',{url:'blob:private',bytes:'private bytes'}]]);
          const exported=ui.sessionData(snapshot,sources); return {text:JSON.stringify(exported),loaded:ui.parseSession(JSON.stringify(exported))};
        })()""")
        self.assertNotIn('blob:', value['text'])
        self.assertNotIn('private bytes', value['text'])
        loaded = value['loaded']
        self.assertEqual([c['name'] for c in loaded['clips']], ['Tide', 'my film.mov'])
        self.assertEqual(loaded['clips'][0]['settings']['blend'], 'difference')
        self.assertEqual(loaded['clips'][1]['settings']['audioLife'], 90)
        self.assertEqual(loaded['clips'][1]['settings']['videoLife'], 8)
        self.assertEqual(loaded['master'], {'volume': .37, 'muted': True})

    def test_untrusted_session_does_not_smuggle_urls_or_out_of_range_values(self):
        value = self.evaluate("""ui.parseSession({format:ui.FORMAT,version:1,master:{volume:900},sequence:{interval:-1},clips:[
          {kind:'audio',name:'a.wav',url:'https://example.test/media',bytes:[1,2,3],settings:{audioRate:999,combFeedback:20,videoEnabled:false,unknown:'x'}}]})""")
        self.assertEqual(value['master']['volume'], 1)
        self.assertEqual(value['sequence']['interval'], 2)
        clip = value['clips'][0]
        self.assertNotIn('url', clip)
        self.assertNotIn('bytes', clip)
        self.assertNotIn('unknown', clip['settings'])
        self.assertEqual(clip['settings']['audioRate'], 3)
        self.assertEqual(clip['settings']['combFeedback'], .75)
        self.assertFalse(clip['settings']['videoEnabled'])

    def test_invalid_schema_and_excess_layers_fail_before_replacing_session(self):
        value = self.evaluate("""[{}, {format:ui.FORMAT,version:2,clips:[]},
          {format:ui.FORMAT,version:1,clips:Array(m.MAX_CLIPS+1).fill({kind:'demo',demo:'tide'})},
          {format:ui.FORMAT,version:1,clips:[{kind:'demo',demo:'remote'}]},
          {format:ui.FORMAT,version:1,clips:[{kind:'remote',url:'https://example.test'}]}
        ].map(data=>{try{ui.parseSession(data);return false;}catch(_){return true;}})""")
        self.assertEqual(value, [True] * 5)

    def test_missing_bottom_local_file_preserves_order_and_settings_until_reselected(self):
        value = self.evaluate("""(()=>{
          const local={kind:'video',name:'bottom.mov',settings:m.normalizeSettings({audioLife:84,blend:'multiply'})};
          const demo={id:'demo',kind:'demo',name:'Prism',settings:m.normalizeSettings({opacity:.3})};
          let clips=[demo]; const snapshot=()=>({clips,volume:.45,muted:false,sequence:{enabled:true,interval:8}});
          const sources=new Map([['demo',{demo:'prism'}]]);
          const slots=[{key:'pending-0',pending:local},{id:'demo'}];
          const savedWhileMissing=ui.parseSession(JSON.stringify(ui.sessionData(snapshot(),sources,slots)));
          const restored={...local,id:'restored'}; clips.push(restored); sources.set('restored',{kind:'video',url:'blob:local'});
          slots[0]={id:'restored'};
          const moves=[]; const engine={snapshot,move:(id,delta)=>{
            moves.push([id,delta]); const index=clips.findIndex(c=>c.id===id); const [c]=clips.splice(index,1); clips.splice(index+delta,0,c);
          }};
          ui.alignEngineOrder(engine,slots);
          return {savedWhileMissing,order:clips.map(c=>c.name),moves,
            savedAfterRestore:ui.sessionData(snapshot(),sources,slots)};
        })()""")
        expected_names = ['bottom.mov', 'Prism']
        self.assertEqual([c['name'] for c in value['savedWhileMissing']['clips']], expected_names)
        self.assertEqual(value['savedWhileMissing']['clips'][0]['settings']['audioLife'], 84)
        self.assertEqual(value['savedWhileMissing']['clips'][0]['settings']['blend'], 'multiply')
        self.assertEqual(value['savedWhileMissing']['clips'][1]['demo'], 'prism')
        self.assertEqual(value['order'], expected_names)
        self.assertEqual(value['moves'], [['restored', -1]])
        self.assertEqual([c['name'] for c in value['savedAfterRestore']['clips']], expected_names)
        self.assertNotIn('blob:', json.dumps(value['savedAfterRestore']))

    def test_pair_move_and_independent_region_trim_are_narrow_bounded_edits(self):
        value = self.evaluate("""(()=>{const s=m.normalizeSettings({timelineStart:3,videoLife:12,audioLife:48});return {
          move:ui.timelineEdit(s,'move','video',1.13,0,true),
          free:ui.timelineEdit(s,'move','audio',1.13,0,false),
          video:ui.timelineEdit(s,'trim','video',-100),
          audio:ui.timelineEdit(s,'trim','audio',1000),original:s};})()""")
        self.assertEqual(value['move'], {'timelineStart': 4.25})
        self.assertAlmostEqual(value['free']['timelineStart'], 4.13)
        self.assertEqual(value['video'], {'videoLife': .25})
        self.assertEqual(value['audio'], {'audioLife': 900})
        self.assertEqual(value['original']['timelineStart'], 3)
        self.assertEqual(value['original']['videoLife'], 12)
        self.assertEqual(value['original']['audioLife'], 48)

    def test_envelope_peak_changes_shared_entrance_and_only_the_selected_lane_level(self):
        value = self.evaluate("""(()=>{const s=m.normalizeSettings({attack:2,opacity:.8,audioGain:.6});return [
          ui.timelineEdit(s,'peak','video',1.5,14.5),ui.timelineEdit(s,'peak','audio',0,-2.9),
          ui.timelineEdit({...s,videoLife:.25},'peak','video',100,100)];})()""")
        self.assertEqual(set(value[0]), {'attack', 'opacity'})
        self.assertEqual(value[0]['attack'], 3.5)
        self.assertAlmostEqual(value[0]['opacity'], .3)
        self.assertEqual(set(value[1]), {'attack', 'audioGain'})
        self.assertAlmostEqual(value[1]['audioGain'], .7)
        self.assertEqual(value[2], {'attack': .125, 'opacity': 0})

    def test_project_retains_transport_and_stable_clip_identity(self):
        value = self.evaluate("""(()=>{const snapshot={volume:.4,muted:false,sequence:{enabled:false,interval:8},
          transport:{mode:'arrange',looping:true,loopStart:4.5,loopEnd:22.25},clips:[
          {id:'clip-7',name:'Tide',kind:'demo',settings:m.normalizeSettings({timelineStart:8.25})}]};
          return ui.parseSession(ui.sessionData(snapshot,new Map([['clip-7',{demo:'tide'}]])));})()""")
        self.assertEqual(value['transport'], {'mode': 'arrange', 'looping': True, 'loopStart': 4.5, 'loopEnd': 22.25})
        self.assertEqual(value['clips'][0]['clipId'], 'clip-7')
        self.assertEqual(value['clips'][0]['settings']['timelineStart'], 8.25)

    def test_identity_validation_and_new_admission_reserve_unresolved_files(self):
        value = self.evaluate("""(()=>{const pending={kind:'video',name:'missing.mov',clipId:'clip-1',settings:m.DEFAULTS};
          const fresh=ui.availableClipId({clips:[{id:'clip-2'}]},[{key:'pending-0',pending},{id:'clip-2'}]);
          const invalid=[['same','same'],['unsafe/path'],['<script>']].map(ids=>{
            try{ui.parseSession({format:ui.FORMAT,version:1,clips:ids.map(clipId=>({clipId,kind:'demo',demo:'tide'}))});return false;}catch(_){return true;}});
          return {fresh,invalid,legacy:ui.parseSession({format:ui.FORMAT,version:1,clips:[{kind:'demo',demo:'tide'}]}).clips.length};})()""")
        self.assertEqual(value['fresh'], 'clip-3')
        self.assertEqual(value['invalid'], [True, True, True])
        self.assertEqual(value['legacy'], 1)

    def test_phone_mov_and_audio_without_mime_are_recognized(self):
        value = self.evaluate("""[
          {name:'IMG_42.MOV',type:''},{name:'field.WAV',type:''},
          {name:'clip',type:'video/mp4'},{name:'take',type:'audio/mp4'},
          {name:'session.json',type:'application/json'}
        ].map(ui.fileKind)""")
        self.assertEqual(value, ['video', 'audio', 'video', 'audio', None])

    def test_envelope_chart_contains_independent_picture_and_sound_departures(self):
        value = self.evaluate("""(()=>{const s=m.normalizeSettings({videoLife:12,audioLife:48,attack:2});
          return [ui.envelopePath(s,s.videoLife),ui.envelopePath(s,s.audioLife)];})()""")
        self.assertIn('L150.0 60.0', value[0])
        self.assertNotIn('L150.0 60.0', value[1])
        self.assertTrue(value[0].endswith('L300.0 60.0'))
        self.assertTrue(value[1].endswith('L300.0 60.0'))


if __name__ == '__main__':
    unittest.main()
