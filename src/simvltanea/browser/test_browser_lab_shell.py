"""Effects Lab delivery, privacy, and selected-layer interaction contracts."""
from __future__ import annotations

from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
import wave

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
        for directive in ["default-src 'none'", "script-src 'self'", 'connect-src https://upload.wikimedia.org',
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

    def test_public_workspace_defaults_empty_without_supplied_clips(self):
        by_id = {a['id']: (tag, a) for tag, a in self.shell.elements if 'id' in a}
        self.assertIn('preview-empty', by_id)
        self.assertIn('timeline-empty', by_id)
        self.assertIn('timeline-import', by_id)
        self.assertIn('bin-import', by_id)
        self.assertIn('open-public-media', by_id)
        self.assertIn('public-media-dialog', by_id)
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
        script = f"const ui=require({json.dumps(str(MODULE))}); const m=global.SimvltaneaLabModel; (async()=>{{console.log(JSON.stringify(await ({expression})));}})().catch(error=>{{console.error(error);process.exit(1);}});"
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

    def test_file_identity_survives_display_trimming_and_unresolved_resave(self):
        value = self.evaluate("""(()=>{
          const fileName='a'.repeat(200)+'7.wav';
          const clip={id:'clip-7',name:fileName,kind:'audio',settings:m.normalizeSettings({audioLife:84})};
          const snapshot={clips:[clip],volume:.45,muted:false,sequence:{enabled:false,interval:8}};
          const sources=new Map([['clip-7',{fileName}]]);
          const saved=ui.sessionData(snapshot,sources);
          const loaded=ui.parseSession(JSON.stringify(saved));
          const reopened=ui.parseSession(ui.sessionData({...snapshot,clips:[]},new Map(),
            [{key:'pending-0',pending:loaded.clips[0]}]));
          return {fileName,saved:saved.clips[0],loaded:loaded.clips[0],reopened:reopened.clips[0]};
        })()""")
        for stage in ('saved', 'loaded', 'reopened'):
            with self.subTest(stage=stage):
                self.assertEqual(value[stage]['fileName'], value['fileName'])
                self.assertEqual(len(value[stage]['name']), 200)
                self.assertEqual(value[stage]['clipId'], 'clip-7')
                self.assertEqual(value[stage]['settings']['audioLife'], 84)

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

    def test_public_catalog_is_fixed_and_rights_are_attached_to_each_source(self):
        value = self.evaluate("""({frozen:Object.isFrozen(ui.PUBLIC_MEDIA)&&ui.PUBLIC_MEDIA.every(Object.isFrozen),
          entries:ui.PUBLIC_MEDIA.map(s=>({id:s.id,kind:s.kind,origin:new URL(s.url).origin,source:s.sourceURL,
            author:s.author,license:s.license,licenseURL:s.licenseURL,mime:s.mime})),unknown:ui.publicMedia('https://example.test/clip.mp4')})""")
        self.assertTrue(value['frozen'])
        self.assertEqual(len(value['entries']), 4)
        self.assertEqual([c['id'] for c in value['entries']], ['rainy-night', 'flowing-stream', 'flowing-water-sound', 'compressor-motor'])
        self.assertEqual([c['kind'] for c in value['entries']], ['video', 'video', 'audio', 'audio'])
        self.assertEqual([c['author'] for c in value['entries']], ['Andy Li', 'Patjos.scot', 'Fg2', 'stephan'])
        for entry in value['entries']:
            self.assertEqual(entry['origin'], 'https://upload.wikimedia.org')
            self.assertTrue(entry['source'].startswith('https://commons.wikimedia.org/wiki/File:'))
            self.assertTrue(entry['licenseURL'].startswith('https://'))
        self.assertEqual([c['license'] for c in value['entries'][:2]], ['CC0 1.0', 'CC0 1.0'])
        self.assertTrue(all('author release' in c['license'] for c in value['entries'][2:]))
        self.assertIsNone(value['unknown'])

    def test_sample_reference_round_trip_retains_order_identity_and_no_url(self):
        value = self.evaluate("""(()=>{const sample={id:'clip-4',name:'Rain',kind:'video',settings:m.normalizeSettings({timelineStart:7.25})};
          const local={name:'mine.wav',kind:'audio',clipId:'clip-1',settings:m.normalizeSettings({audioLife:28})};
          const snapshot={clips:[sample],volume:.4,muted:false,sequence:{enabled:false,interval:8}};
          const sources=new Map([['clip-4',{sampleId:'rainy-night',url:'blob:secret',fileName:'rain.webm'}]]);
          const slots=[{key:'pending-0',pending:local},{id:'clip-4'}];
          const data=ui.sessionData(snapshot,sources,slots);return {text:JSON.stringify(data),parsed:ui.parseSession(data)};})()""")
        self.assertNotIn('blob:', value['text'])
        self.assertNotIn('https://', value['text'])
        self.assertNotIn('url', value['parsed']['clips'][1])
        self.assertEqual([c['clipId'] for c in value['parsed']['clips']], ['clip-1', 'clip-4'])
        self.assertEqual(value['parsed']['clips'][1]['sampleId'], 'rainy-night')
        self.assertEqual(value['parsed']['clips'][1]['settings']['timelineStart'], 7.25)
        self.assertEqual(value['parsed']['clips'][0]['settings']['audioLife'], 28)

    def test_unknown_or_mismatched_sample_references_are_rejected(self):
        value = self.evaluate("""[{sampleId:'https://example.test/a.mp3',kind:'audio'},
          {sampleId:'__proto__',kind:'video'},{sampleId:'rainy-night',kind:'audio'}].map(c=>{
            try{ui.parseSession({format:ui.FORMAT,version:1,clips:[c]});return false;}catch(_){return true;}})""")
        self.assertEqual(value, [True, True, True])

    def test_reasonless_abort_controller_preserves_cancel_and_timeout_errors(self):
        value = self.evaluate("""(async()=>{
          const Native=global.AbortController;
          global.AbortController=class extends Native {
            constructor(){super();Object.defineProperty(this.signal,'reason',{value:undefined});}
            abort(){super.abort();}
          };
          try {
            const caller=new AbortController(),fetcher=()=>new Promise(()=>{});class TestFile{}
            const canceled=ui.fetchPublicMedia('compressor-motor',fetcher,null,TestFile,{signal:caller.signal})
              .then(()=>null,error=>error?.name||'missing reason');
            caller.abort();
            const timeout=await ui.fetchPublicMedia('compressor-motor',fetcher,null,TestFile,{timeoutMs:10})
              .then(()=>null,error=>error?.name||'missing reason');
            return {canceled:await canceled,timeout};
          }finally{global.AbortController=Native;}
        })()""")
        self.assertEqual(value, {'canceled': 'AbortError', 'timeout': 'TimeoutError'})

    def test_public_download_deadline_aborts_a_fetch_that_never_resolves(self):
        value = self.evaluate("""(async()=>{
          let aborted=false;const fetcher=(_,options)=>{options.signal?.addEventListener('abort',()=>{aborted=true;});return new Promise(()=>{});};
          class TestFile{}
          const result=await Promise.race([
            ui.fetchPublicMedia('compressor-motor',fetcher,null,TestFile,{timeoutMs:10})
              .then(()=>({name:'unexpected success'}),error=>({name:error.name,message:error.message})),
            new Promise(resolve=>setTimeout(()=>resolve({name:'still pending'}),100))]);
          return {result,aborted};})()""")
        self.assertEqual(value['result']['name'], 'TimeoutError')
        self.assertIn('timed out', value['result']['message'])
        self.assertTrue(value['aborted'])

    def test_canceled_body_cannot_cache_or_finish_after_a_new_download(self):
        value = self.evaluate("""(async()=>{
          const old=new AbortController(),fresh=new AbortController();let release,files=0,writes=0;
          const held={ok:true,type:'cors',clone(){return this;},blob:()=>new Promise(resolve=>{release=resolve;})};
          const storage={open:async()=>({match:async()=>null,put:async()=>{writes++;}})};
          class TestFile{constructor(parts){files++;this.size=parts[0].size;}}
          const first=ui.fetchPublicMedia('compressor-motor',async()=>held,storage,TestFile,{signal:old.signal})
            .then(()=>({name:'unexpected success'}),error=>({name:error.name}));
          while(!release)await new Promise(resolve=>setImmediate(resolve));
          old.abort(new DOMException('Download canceled.','AbortError'));
          const second=await ui.fetchPublicMedia('compressor-motor',async()=>new Response('new file',
            {headers:{'Content-Type':'audio/mpeg'}}),storage,TestFile,{signal:fresh.signal});
          release(new Blob(['old file'],{type:'audio/mpeg'}));
          const result=await first;await new Promise(resolve=>setImmediate(resolve));
          return {result,newSize:second.size,files,writes,freshAborted:fresh.signal.aborted};})()""")
        self.assertEqual(value, {'result': {'name': 'AbortError'}, 'newSize': 8, 'files': 1,
                                 'writes': 1, 'freshAborted': False})

    def test_public_download_omits_credentials_and_reuses_browser_cache(self):
        value = self.evaluate("""(async()=>{
          const calls=[],saved=new Map();const response={ok:true,status:200,type:'cors',blob:async()=>new Blob(['media']),clone(){return this;}};
          const fetcher=async(url,options)=>{calls.push({url,options});return response;};
          const storage={open:async()=>({match:async key=>saved.get(key),put:async(key,res)=>saved.set(key,res)})};
          class TestFile{constructor(parts,name,options){this.name=name;this.type=options.type;this.size=parts[0].size;}}
          const a=await ui.fetchPublicMedia('compressor-motor',fetcher,storage,TestFile);
          const b=await ui.fetchPublicMedia('compressor-motor',fetcher,storage,TestFile);
          return {calls,a,b,keys:Array.from(saved.keys())};})()""")
        self.assertEqual(len(value['calls']), 1)
        options = value['calls'][0]['options']
        self.assertEqual(options['method'], 'GET')
        self.assertEqual(options['credentials'], 'omit')
        self.assertEqual(options['mode'], 'cors')
        self.assertEqual(options['referrerPolicy'], 'no-referrer')
        self.assertEqual(options['redirect'], 'error')
        self.assertNotIn('body', options)
        self.assertTrue(value['calls'][0]['url'].startswith('https://upload.wikimedia.org/'))
        self.assertEqual(value['a']['type'], 'audio/mpeg')
        self.assertEqual(value['a'], value['b'])
        self.assertEqual(len(value['keys']), 1)

    def test_unknown_public_id_never_fetches_and_http_errors_do_not_make_files(self):
        value = self.evaluate("""(async()=>{let calls=0,files=0;class TestFile{constructor(){files++;}}
          const fetcher=async()=>{calls++;return {ok:false,status:403,type:'cors'};};const errors=[];
          for(const id of ['not-in-catalog','rainy-night']){try{await ui.fetchPublicMedia(id,fetcher,null,TestFile);}catch(e){errors.push(e.message);}}
          let deleted='';await ui.clearPublicMediaCache({delete:async key=>{deleted=key;return true;}});
          return {calls,files,errors,deleted};})()""")
        self.assertEqual(value['calls'], 1)
        self.assertEqual(value['files'], 0)
        self.assertEqual(len(value['errors']), 2)
        self.assertIn('403', value['errors'][1])
        self.assertEqual(value['deleted'], 'independent-loop-compositor-effects-lab:public-media-v1')

    def test_content_identity_round_trip_and_same_metadata_different_bytes(self):
        value = self.evaluate("""(async()=>{
          const crypto=require('node:crypto').webcrypto;
          const a=new Blob(['first']),b=new Blob(['other']);
          const one=await ui.fileIdentity(a,crypto),two=await ui.fileIdentity(b,crypto);
          const clip={id:'clip-1',name:'take.wav',kind:'audio',settings:{},...one};
          const snapshot={clips:[clip],volume:.4,sequence:{}};
          const saved=ui.sessionData(snapshot,new Map([['clip-1',{fileName:'take.wav',...one}]]));
          const parsed=ui.parseSession(saved);
          const pending=ui.sessionData({...snapshot,clips:[]},new Map(),[{key:'pending-0',pending:parsed.clips[0]}]);
          let missingCrypto;try{await ui.fileIdentity(a,{});}catch(e){missingCrypto=e.message;}
          return {one,two,saved,parsed,pending,missingCrypto};})()""")
        self.assertNotEqual(value['one']['fileSha256'], value['two']['fileSha256'])
        self.assertEqual(value['one']['fileSize'], value['two']['fileSize'])
        for key in ('saved', 'parsed', 'pending'):
            self.assertEqual(value[key]['clips'][0]['fileSha256'], value['one']['fileSha256'])
            self.assertEqual(value[key]['clips'][0]['fileSize'], 5)
        self.assertIn('HTTPS', value['missingCrypto'])

    def test_mixed_saved_identity_keeps_unknown_same_name_explicit_through_resave(self):
        value = self.evaluate("""(()=>{
          const parsed=ui.parseSession({format:ui.FORMAT,version:1,clips:[
            {clipId:'one',kind:'audio',name:'take.wav',fileName:'take.wav',fileSha256:'a'.repeat(64),fileSize:20},
            {clipId:'two',kind:'audio',name:'take.wav',fileName:'take.wav'}]});
          const pending=ui.sessionData({clips:[],volume:.4,sequence:{}},new Map(),
            [{key:'pending-1',pending:parsed.clips[1]}]);
          return {parsed,reopened:ui.parseSession(pending)};})()""")
        self.assertNotIn('requiresFileChoice', value['parsed']['clips'][0])
        self.assertTrue(value['parsed']['clips'][1]['requiresFileChoice'])
        self.assertTrue(value['reopened']['clips'][0]['requiresFileChoice'])

    def test_invalid_file_identity_is_rejected_before_replacing_session(self):
        value = self.evaluate("""[
          {fileSha256:'not-a-hash',fileSize:5},{fileSha256:'a'.repeat(64)},
          {fileSha256:'a'.repeat(64),fileSize:-1},{fileSize:5}
        ].map(identity=>{try{ui.parseSession({format:ui.FORMAT,version:1,clips:[
          {kind:'audio',name:'take.wav',...identity}]});return false;}catch(_){return true;}})""")
        self.assertEqual(value, [True] * 4)

    def test_invalid_public_body_is_not_cached_and_retry_fetches_again(self):
        value = self.evaluate("""(async()=>{
          let calls=0;const values=new Map(),errors=[];
          const storage={open:async()=>({match:async key=>values.get(key)?.clone(),
            put:async(key,response)=>values.set(key,response.clone()),delete:async key=>values.delete(key)})};
          const fetcher=async()=>new Response(++calls===1?'':'media',{status:200,headers:{'Content-Type':'audio/mpeg'}});
          class TestFile{constructor(parts){this.size=parts[0].size;}}
          try{await ui.fetchPublicMedia('compressor-motor',fetcher,storage,TestFile);}catch(e){errors.push(e.message);}
          const retry=await ui.fetchPublicMedia('compressor-motor',fetcher,storage,TestFile);
          return {calls,errors,size:retry.size,cached:values.size};})()""")
        self.assertEqual(value['calls'], 2)
        self.assertEqual(value['size'], 5)
        self.assertEqual(value['cached'], 1)
        self.assertEqual(len(value['errors']), 1)

    def test_invalid_cached_public_body_is_evicted_and_refetched(self):
        value = self.evaluate("""(async()=>{
          let calls=0,deletes=0;let cached=new Response('',{status:200});
          const storage={open:async()=>({match:async()=>cached?.clone(),
            put:async(_,response)=>{cached=response.clone();},delete:async()=>{deletes++;cached=null;}})};
          const fetcher=async()=>{calls++;return new Response('media',{status:200,headers:{'Content-Type':'audio/mpeg'}});};
          class TestFile{constructor(parts){this.size=parts[0].size;}}
          const file=await ui.fetchPublicMedia('compressor-motor',fetcher,storage,TestFile);
          return {calls,deletes,size:file.size};})()""")
        self.assertEqual(value, {'calls': 1, 'deletes': 1, 'size': 5})

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


class EffectsLabLocalRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest('Playwright is required for local-media restore tests')
        from simvltanea.browser.test_browser_runtime import browser_executable
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(),
                                            headless=True, args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open_lab(self, origin='http://localhost'):
        files = lab_files()
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        def serve(route):
            name = route.request.url.rsplit('/', 1)[-1]
            route.fulfill(status=200 if name in files else 404, body=files.get(name, b''),
                          content_type='text/html' if name.endswith('.html') else 'application/javascript')
        page.route(origin + '/**', serve)
        page.goto(origin + '/lab.html')
        self.ready(page)
        return page

    def ready(self, page):
        page.wait_for_function("() => !document.querySelector('#lab-app').classList.contains('busy')")

    def wav_file(self, frames=2000, sample=b'\0\0'):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(sample * frames)
        return {'name': 'take.wav', 'mimeType': 'audio/wav', 'buffer': buffer.getvalue()}

    def save_reopen(self, page):
        page.locator('#save-settings').click()
        page.locator('#reset-session').click()
        self.ready(page)
        page.locator('#load-settings').click()
        self.ready(page)

    def test_same_filename_restores_only_matching_content_and_keeps_missing_identity(self):
        page = self.open_lab()
        for file in (self.wav_file(), self.wav_file(4000)):
            page.locator('#media-input').set_input_files(file)
            self.ready(page)
        self.save_reopen(page)
        page.locator('#media-input').set_input_files(self.wav_file(6000))
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 2)
        self.assertIn('contents do not match', page.locator('#lab-status').inner_text())
        page.locator('#media-input').set_input_files({**self.wav_file(), 'name': 'renamed.wav'})
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 1)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 1)
        page.locator('#save-settings').click()
        saved = page.evaluate('() => JSON.parse(localStorage.getItem(SimvltaneaLabUI.STORAGE_KEY))')
        self.assertNotEqual(saved['clips'][0]['fileSha256'], saved['clips'][1]['fileSha256'])
        page.locator('#media-input').set_input_files(self.wav_file(4000))
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 0)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.map(c=>c.audio.duration)'), [.25, .5])

    def test_duplicate_same_content_restores_both_and_equal_file_metadata_does_not_merge_bin(self):
        import base64
        page = self.open_lab()
        def select(file):
            page.evaluate('''encoded => {const transfer=new DataTransfer();transfer.items.add(new File([
              Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))],'take.wav',{type:'audio/wav',lastModified:123}));
              const input=document.querySelector('#media-input');input.files=transfer.files;input.dispatchEvent(new Event('change'));}''',
                          base64.b64encode(file['buffer']).decode())
            self.ready(page)
        select(self.wav_file())
        select(self.wav_file(sample=b'\1\0'))
        self.assertEqual(page.locator('#media-bin-list [data-asset]').count(), 2)
        page.locator('#duplicate-clip').click()
        self.ready(page)
        self.save_reopen(page)
        select(self.wav_file(sample=b'\1\0'))
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 2)
        self.assertEqual(page.locator('.layer.pending').count(), 1)

    def test_legacy_same_names_require_choosing_a_specific_missing_clip(self):
        page = self.open_lab()
        session = {'format': 'independent-loop-compositor-effects-lab', 'version': 1,
                   'clips': [{'clipId': f'clip-{i}', 'kind': 'audio', 'name': 'take.wav', 'fileName': 'take.wav'} for i in (1, 2)]}
        page.locator('#settings-input').set_input_files({'name': 'project.json', 'mimeType': 'application/json',
                                                        'buffer': json.dumps(session).encode()})
        self.ready(page)
        page.locator('#media-input').set_input_files(self.wav_file())
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 2)
        self.assertIn('Choose', page.locator('#lab-status').inner_text())
        page.locator('#view-perform').click()
        with page.expect_file_chooser() as chooser:
            page.locator('[data-layer="pending-0"] [data-action="restore"]').first.click()
        chooser.value.set_files(self.wav_file())
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 1)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 1)
        # The original ambiguity persists after one member is resolved.
        page.locator('#media-input').set_input_files(self.wav_file())
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 1)
        self.save_reopen(page)
        for _ in range(2):
            page.locator('#media-input').set_input_files(self.wav_file())
            self.ready(page)
            self.assertEqual(page.locator('.layer.pending').count(), 1)
        page.locator('#view-perform').click()
        with page.expect_file_chooser() as chooser:
            page.locator('.layer.pending [data-action="restore"]').first.click()
        chooser.value.set_files(self.wav_file(4000))
        self.ready(page)
        self.assertEqual(page.locator('.layer.pending').count(), 0)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.map(c=>c.audio.duration)'), [.25, .5])

    def test_cancel_held_download_preserves_playing_clips_and_allows_retry(self):
        page = self.open_lab()
        page.set_default_timeout(3000)
        page.locator('#media-input').set_input_files(self.wav_file(80000))
        self.ready(page)
        page.locator('#transport-play').click()
        page.wait_for_function('() => SimvltaneaLabUI.engine.playing')
        before = page.evaluate('''() => {window.existing=SimvltaneaLabUI.engine.clips[0].audioElement;
          return {id:SimvltaneaLabUI.engine.clips[0].id,time:existing.currentTime};}''')
        requests = []
        def public_response(route):
            requests.append(route)
            if len(requests) > 1:
                route.fulfill(status=200, content_type='audio/mpeg',
                              headers={'Access-Control-Allow-Origin': '*'}, body=self.wav_file()['buffer'])
        page.route('https://upload.wikimedia.org/**', public_response)
        page.evaluate('''() => {const Native=AbortController;globalThis.AbortController=class extends Native {
          constructor(){super();Object.defineProperty(this.signal,'reason',{value:undefined});}abort(){super.abort();}};}''')
        page.locator('#open-public-media').click()
        with page.expect_request(lambda request: request.url.startswith('https://upload.wikimedia.org/')):
            page.locator('[data-public-media="compressor-motor"]').click()
        page.locator('#cancel-public-download').click()
        self.ready(page)
        self.assertTrue(page.locator('#cancel-public-download').is_hidden())
        self.assertTrue(page.locator('#transport-play').is_enabled())
        self.assertTrue(page.locator('#reset-session').is_enabled())
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.clips.map(c=>c.id)'), [before['id']])
        self.assertTrue(page.evaluate('() => existing===SimvltaneaLabUI.engine.clips[0].audioElement && !existing.paused'))
        self.assertGreater(page.evaluate('() => existing.currentTime'), before['time'])
        # Even a late response to the canceled request cannot become a source.
        if requests:
            try:
                requests[0].fulfill(status=200, content_type='audio/mpeg',
                                    headers={'Access-Control-Allow-Origin': '*'}, body=self.wav_file()['buffer'])
            except Exception:
                pass  # Browser cancellation may already have closed the route.
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.clips.length'), 1)
        self.assertFalse(page.evaluate('''async () => Boolean(await (await caches.open(SimvltaneaLabUI.MEDIA_CACHE))
          .match(SimvltaneaLabUI.publicMedia('compressor-motor').url))'''))
        page.locator('[data-public-media="compressor-motor"]').click()
        self.ready(page)
        self.assertEqual(len(requests), 2)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.clips.length'), 2)
        self.assertTrue(page.evaluate('() => existing===SimvltaneaLabUI.engine.clips[0].audioElement'))

    def test_failed_public_decode_evicts_caches_and_retry_loads_new_bytes(self):
        page = self.open_lab()
        calls = []
        def public_response(route):
            calls.append(route.request.url)
            route.fulfill(status=200, content_type='audio/mpeg',
                          headers={'Access-Control-Allow-Origin': '*'},
                          body=b'not playable media' if len(calls) == 1 else self.wav_file()['buffer'])
        page.route('https://upload.wikimedia.org/**', public_response)
        page.locator('#open-public-media').click()
        page.locator('[data-public-media="compressor-motor"]').click()
        self.ready(page)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 0)
        self.assertIn('Cannot decode', page.locator('#public-media-status').inner_text())
        self.assertEqual(page.locator('#media-bin-list [data-asset]').count(), 0)
        page.locator('[data-public-media="compressor-motor"]').click()
        self.ready(page)
        self.assertEqual(len(calls), 2)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 1)
        page.locator('#close-public-media').click()
        page.locator('#media-bin-list [data-asset]').click()
        self.ready(page)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 2)
        self.assertEqual(len(calls), 2)

    def test_insecure_context_does_not_guess_a_content_identity(self):
        page = self.open_lab('http://lab.test')
        page.locator('#media-input').set_input_files(self.wav_file())
        self.ready(page)
        self.assertEqual(page.evaluate('() => SimvltaneaLabUI.engine.snapshot().clips.length'), 0)
        self.assertIn('HTTPS', page.locator('#lab-status').inner_text())

    def test_reselect_long_names_restores_all_eight_occupied_slots(self):
        files = lab_files()
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        def serve(route):
            name = route.request.url.rsplit('/', 1)[-1]
            route.fulfill(status=200 if name in files else 404, body=files.get(name, b''),
                          content_type='text/html' if name.endswith('.html') else 'application/javascript')
        page.route('http://localhost/**', serve)
        page.goto('http://localhost/lab.html')
        page.wait_for_function("() => document.querySelector('#lab-app:not(.busy)') && globalThis.SimvltaneaLabUI")
        names = ['a' * 200 + str(i) + '.wav' for i in range(8)]
        clips = [{'clipId': f'clip-{i + 1}', 'name': name, 'fileName': name, 'kind': 'audio',
                  'settings': {'audioLife': 40 + i, 'timelineStart': i * 2.5}}
                 for i, name in enumerate(names)]
        session = {'format': 'independent-loop-compositor-effects-lab', 'version': 1, 'clips': clips}
        page.locator('#settings-input').set_input_files(
            {'name': 'project.json', 'mimeType': 'application/json', 'buffer': json.dumps(session).encode()})
        page.wait_for_function("() => !document.querySelector('#lab-app').classList.contains('busy') && document.querySelectorAll('.layer.pending').length === 8")
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b'\0\0' * 2000)
        # Reversed selection order must fill the saved slots, not create new clips.
        page.locator('#media-input').set_input_files(
            [{'name': name, 'mimeType': 'audio/wav', 'buffer': buffer.getvalue()} for name in reversed(names)])
        page.wait_for_function("() => !document.querySelector('#lab-app').classList.contains('busy')")
        self.assertEqual(page.locator('.layer.pending').count(), 0,
                         page.locator('#lab-status').inner_text())
        self.assertEqual(page.locator('.layer').count(), 8)
        page.locator('#save-settings').click()
        saved = page.evaluate('() => JSON.parse(localStorage.getItem(SimvltaneaLabUI.STORAGE_KEY))')
        self.assertEqual([clip['fileName'] for clip in saved['clips']], names)
        self.assertEqual([clip['clipId'] for clip in saved['clips']], [f'clip-{i + 1}' for i in range(8)])
        self.assertEqual([clip['settings']['audioLife'] for clip in saved['clips']], list(range(40, 48)))
        self.assertEqual([clip['settings']['timelineStart'] for clip in saved['clips']], [i * 2.5 for i in range(8)])


if __name__ == '__main__':
    unittest.main()
