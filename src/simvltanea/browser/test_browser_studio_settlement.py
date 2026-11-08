"""Studio must publish the residents that actually survived a media handoff.

These tests use the real Studio compiler, controls, assets, and Session pipeline.
The sole playback fault is a primed successor whose play promise resolves while
its native media element remains paused, reproducing the hosted readiness fault.
"""
from __future__ import annotations

import json
import hashlib
import shutil
import unittest
from fractions import Fraction
from pathlib import Path

from simvltanea.browser import test_browser_studio as studio_tests


PROOFS = Path(__file__).resolve().parents[3] / 'var' / 'proofs' / 'studio-settlement'
COMPILER_OBSERVER = r'''(() => {
  const NativeWorker = Worker;
  window.settlementCompilers = new Set();
  window.settlementHeldCompilers = [];
  window.Worker = class extends NativeWorker {
    set onmessage(handler) {
      this.settlementMessageHandler=handler;
      super.onmessage=event=>{
        handler.call(this,event);
        if(!this.settlementRecovery || !window.settlementSupersedeAfterDelivery) return;
        const slot=window.settlementSupersedeAfterDelivery;
        window.settlementSupersedeAfterDelivery=null;
        // The actual handler has resolved/rejected the compiler promise and
        // cleared its job. A same-task edit now precedes its await continuation
        // without merely cancelling that still-pending compiler job.
        document.querySelector(`#stage .loop[data-loop-id="${slot}"]`).click();
        window.settlementSuperseded=true;
      };
    }
    get onmessage() { return this.settlementMessageHandler; }
    postMessage(...args) {
      settlementCompilers.add(this);
      const deferred=window.compositionRuntime?.events.some(e=>e.type==='handoff-deferred');
      const fail=window.settlementFailNextCompilation || (window.settlementFailRecoveryCompilation && deferred);
      if(fail) {
        window.settlementFailNextCompilation=false;
        window.settlementFailRecoveryCompilation=false;
        args[0]=structuredClone(args[0]);
        args[0].sources[0].duration='invalid duration';
      }
      const send=()=>{if(!this.settlementTerminated) super.postMessage(...args);};
      this.settlementRecovery=Boolean(deferred && (window.holdSettlementRecovery || fail));
      if(this.settlementRecovery || fail)
        settlementHeldCompilers.push({worker:this,input:structuredClone(args[0]),send});
      else send();
    }
    terminate() { this.settlementTerminated=true; settlementCompilers.delete(this); return super.terminate(); }
  };
  window.releaseSettlementCompilers=()=>{
    window.holdSettlementRecovery=false;
    settlementHeldCompilers.splice(0).forEach(job=>job.send());
  };
})();'''


class StudioSettlementTests(unittest.TestCase):
    """Delegate fixture setup without collecting StudioLibraryTests' test methods."""

    @classmethod
    def setUpClass(cls):
        studio_tests.StudioLibraryTests.setUpClass.__func__(cls)
        # A distinct 30 fps asset behind one logical library identity exercises
        # retained bytes after the mode switch replaces the library item array.
        variant_site = studio_tests.LIBRARY_SITES / 'settlement-variant'
        shutil.copytree(studio_tests.LIBRARY_SITES / 'good', variant_site)
        temporary = variant_site / 'variant.mp4'
        studio_tests.ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=192x144:rate=30,hue=h=217',
                            '-f', 'lavfi', '-i', 'sine=frequency=733:sample_rate=48000',
                            '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-ac', '1', '-shortest', '-movflags', '+faststart', str(temporary))
        contents = temporary.read_bytes()
        cls.variant_sha = hashlib.sha256(contents).hexdigest()
        variant_id = cls.variant_sha[:12]
        temporary.rename(variant_site / 'library' / 'clips' / f'{variant_id}.mp4')
        manifest = json.loads(json.dumps(cls.manifest))
        clip = next(item for item in manifest['clips'] if item['id'] == cls.ids[0])
        clip['variants'] = {'boomerang': {
            'id': variant_id, 'file': f'clips/{variant_id}.mp4', 'bytes': len(contents),
            'width': 192, 'height': 144, 'orientation': 'landscape', 'duration_seconds': 2,
            'fps': 30, 'frame_count': 60, 'seam_offset_seconds': 1,
            'has_audio': True, 'envelope_hz': 10, 'rms_envelope': [.1] * 20,
            'lufs_integrated': -20, 'peak_dbfs': -10,
        }}
        (variant_site / 'library' / 'manifest.json').write_text(json.dumps(manifest))
        small_site = studio_tests.LIBRARY_SITES / 'settlement-three'
        shutil.copytree(studio_tests.LIBRARY_SITES / 'good', small_site)
        small_manifest = {'schema': cls.manifest['schema'],
                          'clips': [cls.by_id[clip_id] for clip_id in cls.ids[:3]]}
        (small_site / 'library' / 'manifest.json').write_text(json.dumps(small_manifest))

    @classmethod
    def tearDownClass(cls):
        studio_tests.StudioLibraryTests.tearDownClass.__func__(cls)

    open = studio_tests.StudioLibraryTests.open
    snapshot = studio_tests.StudioLibraryTests.snapshot
    playing = studio_tests.StudioLibraryTests.playing
    unlock = studio_tests.StudioLibraryTests.unlock
    tap = studio_tests.StudioLibraryTests.tap

    def ready(self, *, count=4, init_script='', site='good'):
        page = self.open(site=site, query='?seed=99&mix=s' + '.'.join(map(str, range(count))) + '&evolve=0&proof=1',
                         has_touch=True, init_script=COMPILER_OBSERVER + init_script)
        self.playing(page, count)
        self.unlock(page)
        self.settled(page)
        page.evaluate('''() => {
          const r=compositionRuntime;
          window.settlementFault={incoming:null};
          window.settlementBefore={context:r.audio.context,clock:r.clock,generation:r.generation,
            plan:structuredClone(r.plan),selection:SimvltaneaStudio.snapshot().selection,
            mix:new URLSearchParams(location.search).get('mix'),
            residents:[...r.nodes.values()].map(n=>({id:n.id,node:n,media:n.media,deck:n.active,
              item:n.item,birth:n.birthTime,audio:n.audio,url:n.active.url,callbacks:n.callbacks}))};
        }''')
        return page

    def settled(self, page):
        page.wait_for_function('''() => {
          const r=compositionRuntime;
          return r.ready && !r.draining && !r.pending && !settlementCompilers.size &&
            !SimvltaneaStudio.snapshot().busy && [...r.nodes.values()].every(n=>!n.busy);
        }''', timeout=30000)

    def defer(self, page, slot='loop-1'):
        page.evaluate('''slot => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.settlementFault={slot,applied:false,incoming:null};
          r.prime=async (...args)=>{
            await prime(...args);
            const [deck,node]=args;
            if(node.id!==slot || settlementFault.applied) return;
            settlementFault.applied=true; settlementFault.incoming=deck.media;
            settlementFault.itemName=deck.item.name;
            deck.media.pause(); deck.media.play=()=>Promise.resolve();
          };
          window.restoreSettlementFault=()=>{
            r.prime=prime;
            if(settlementFault.incoming) delete settlementFault.incoming.play;
          };
        }''', slot)

    def tap_panel(self, page, slot):
        panel = page.locator(f'#stage .loop[data-loop-id="{slot}"]')
        panel.click(position={'x': 20, 'y': 30})

    def edit_two_new_panels(self, page):
        # Choose test input randomness, not expected output: both requested
        # assets must be new so resident-preserving normalization cannot turn
        # this intended partial-success case into a permutation-only request.
        page.evaluate('''manifest => {
          const api=SimvltaneaStudio, clips=api.libraryClips(manifest), state=api.snapshot();
          const before=state.selection.map(id=>clips.findIndex(clip=>clip.id===id));
          let selected=null;
          for(let seed=1;seed<1000;seed++) {
            const [first]=api.chooseClips(clips,1,state.family,api.seededRandom(seed),before.slice(1),[before[0]]);
            const keep=[first,...before.slice(2)];
            const [second]=api.chooseClips(clips,1,state.family,api.seededRandom(seed),keep,[before[1]]);
            if(!before.includes(first) && !before.includes(second)) {selected=seed;break;}
          }
          if(selected===null) throw new Error('Fixture needs two genuinely new panel edits');
          const descriptor=Object.getOwnPropertyDescriptor(crypto,'getRandomValues');
          Object.defineProperty(crypto,'getRandomValues',{configurable:true,value:array=>{array[0]=selected;return array;}});
          try {
            for(const id of ['loop-1','loop-2']) document.querySelector(`#stage .loop[data-loop-id="${id}"]`).click();
          } finally {
            if(descriptor) Object.defineProperty(crypto,'getRandomValues',descriptor);
            else delete crypto.getRandomValues;
          }
        }''', self.manifest)

    def wait_deferred(self, page, count=1):
        page.wait_for_function('''count => compositionRuntime.events.filter(
          e=>e.type==='handoff-deferred').length >= count''', arg=count, timeout=15000)
        self.settled(page)

    def report(self, page, name):
        result = page.evaluate('''async () => {
          const r=compositionRuntime, plan=await compositionIO.plan();
          const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
            byte=>byte.toString(16).padStart(2,'0')).join('');
          const exported=[];
          for(const source of plan.sources) {
            try { const bytes=await compositionIO.bytes(source);
              exported.push({id:source.id,sha:await digest(bytes),bytes:bytes.byteLength,type:compositionIO.type(source)});
            } catch(error) { exported.push({id:source.id,error:String(error)}); }
          }
          return {snapshot:SimvltaneaStudio.snapshot(),plan:structuredClone(plan),runtimePlan:structuredClone(r.plan),
            exported,mix:new URLSearchParams(location.search).get('mix'),
            actual:[...r.nodes.values()].map(n=>({id:n.id,name:n.item.name,sha:n.item.sha256,size:n.item.size,
              duration:n.item.quantized.duration,audio:n.item.audioStream,type:n.item.type})),
            residents:settlementBefore.residents.map(b=>{const n=r.nodes.get(b.id);return {id:b.id,
              sameNode:n===b.node,sameMedia:n?.media===b.media,sameDeck:n?.active===b.deck,
              sameItem:n?.item===b.item,sameBirth:n?.birthTime===b.birth,sameAudio:n?.audio===b.audio,
              sameURL:n?.active?.url===b.url,advancing:n?.callbacks>b.callbacks,paused:n?.media.paused};}),
            context:r.audio.context===settlementBefore.context,clock:r.clock===settlementBefore.clock,
            generation:r.generation===settlementBefore.generation,failure:r.lastFailure,
            deferred:r.events.filter(e=>e.type==='handoff-deferred'),permits:r.activeStandbys,
            faultItem:settlementFault.itemName,
            incomingReleased:!settlementFault.incoming?.hasAttribute('src')};
        }''')
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / f'{name}.json').write_text(json.dumps(result, indent=2) + '\n')
        return result

    def assert_plan_matches_residents(self, result):
        self.assertEqual(result['snapshot']['selection'], [item['name'] for item in result['actual']])
        self.assertEqual(result['plan'], result['runtimePlan'])
        self.assertEqual(len(result['plan']['sources']), len(result['actual']))
        for source, track, asset, exported in zip(result['plan']['sources'], result['plan']['tracks'],
                                                 result['actual'], result['exported']):
            with self.subTest(slot=asset['id']):
                self.assertEqual(track['id'], asset['id'])
                self.assertEqual(source['sha256'], asset['sha'])
                self.assertEqual(source['duration'], asset['duration'])
                self.assertEqual(source['bytes'], asset['size'])
                self.assertEqual(source['audio_stream'], asset['audio'])
                self.assertEqual(exported, dict(id=source['id'], sha=asset['sha'], bytes=asset['size'], type=asset['type']))
                self.assertTrue(all(span['source'] == source['id'] for span in track['spans']))
                period = Fraction(asset['duration']) * result['plan']['fps']
                self.assertEqual(period.denominator, 1)
                self.assertEqual([span['frame'] for span in track['spans']],
                                 list(range(0, result['plan']['frames'], int(period))))
                self.assertTrue(all(Fraction(span['source_offset']) == 0 for span in track['spans']))

    def test_deferred_panel_tap_restores_selection_share_link_and_export(self):
        page = self.ready()
        before = page.evaluate('({selection:settlementBefore.selection,mix:settlementBefore.mix,plan:settlementBefore.plan})')
        self.defer(page)
        self.tap_panel(page, 'loop-1')
        self.wait_deferred(page)
        result = self.report(page, 'deferred-panel-tap')
        self.assertEqual(len(result['deferred']), 1)
        self.assertTrue(result['incomingReleased'])
        self.assertEqual(result['permits'], 0)
        self.assertIsNone(result['failure'])
        self.assertTrue(result['context'] and result['clock'] and result['generation'])
        self.assertTrue(all(all(row[key] for key in ('sameNode', 'sameMedia', 'sameDeck', 'sameItem',
            'sameBirth', 'sameAudio', 'sameURL', 'advancing')) and not row['paused'] for row in result['residents']))
        self.assertEqual(result['snapshot']['selection'], before['selection'])
        self.assertEqual(result['mix'], before['mix'])
        self.assert_plan_matches_residents(result)
        self.assertEqual(result['plan']['tracks'], before['plan']['tracks'])

    def test_partial_two_slot_request_keeps_successful_sibling_and_exports_actual_mix(self):
        page = self.ready()
        before = page.evaluate('settlementBefore.selection')
        self.defer(page, 'loop-2')
        # Both public clicks run before either asynchronous compiler can finish.
        # The second request therefore contains both edits; only slot two stalls.
        self.edit_two_new_panels(page)
        self.wait_deferred(page)
        result = self.report(page, 'partial-two-slot')
        names = [item['name'] for item in result['actual']]
        self.assertNotEqual(names[0], before[0], 'the first replacement must genuinely commit')
        self.assertEqual(names[1:], before[1:])
        self.assertFalse(result['residents'][0]['sameMedia'])
        for sibling in result['residents'][1:]:
            self.assertTrue(all(sibling[key] for key in ('sameNode', 'sameMedia', 'sameDeck', 'sameItem',
                'sameBirth', 'sameAudio', 'sameURL', 'advancing')), sibling)
        self.assertTrue(result['context'] and result['clock'] and result['generation'])
        self.assertIsNone(result['failure'])
        self.assert_plan_matches_residents(result)
        expected_mix = 's' + '.'.join(str(self.ids.index(name)) for name in names)
        self.assertEqual(result['mix'], expected_mix)

    def test_retained_variant_keeps_exact_bytes_when_another_panel_is_tapped(self):
        page = self.ready(site='settlement-variant')
        self.assertEqual(page.evaluate("compositionRuntime.nodes.get('loop-1').item.sha256"), self.variant_sha)
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        result = self.report(page, 'retained-variant')
        self.assertEqual(result['snapshot']['loopMode'], 'forward')
        self.assertEqual(result['actual'][0]['sha'], self.variant_sha)
        self.assert_plan_matches_residents(result)
        page.evaluate('restoreSettlementFault()')
        self.tap_panel(page, 'loop-2')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-2').item!==settlementBefore.residents[1].item")
        self.settled(page)
        result = self.report(page, 'retained-variant-next-tap')
        self.assertEqual(result['actual'][0]['sha'], self.variant_sha)
        self.assertTrue(all(result['residents'][0][key] for key in ('sameNode', 'sameMedia', 'sameDeck',
            'sameItem', 'sameBirth', 'sameAudio', 'sameURL', 'advancing')))
        self.assert_plan_matches_residents(result)

    def test_partial_personal_import_keeps_foreign_resident_during_next_tap(self):
        page = self.ready()
        self.defer(page, 'loop-2')
        # Five admitted files leave a spare after the mobile four-panel limit.
        files = []
        for index, clip_id in enumerate(self.ids[10:15]):
            source = studio_tests.LIBRARY / 'clips' / f'{clip_id}.mp4'
            files.append({'name': f'personal-{index}.mp4', 'mimeType': 'video/mp4', 'buffer': source.read_bytes()})
        page.set_input_files('#files', files)
        self.wait_deferred(page)
        result = self.report(page, 'partial-personal-import')
        self.assertEqual(result['snapshot']['source'], 'own')
        self.assertEqual(len(result['actual']), 4)
        self.assertEqual(result['actual'][1]['name'], self.ids[1])
        self.assertTrue(result['residents'][1]['sameMedia'] and result['residents'][1]['sameItem'])
        self.assertTrue(all(item['name'].startswith('personal-') for index, item in enumerate(result['actual']) if index != 1))
        self.assert_plan_matches_residents(result)
        self.assertIsNone(result['mix'], 'a mixed private composition must not advertise a reproducible library mix')
        page.evaluate('''() => {
          restoreSettlementFault();
          window.foreignResident=compositionRuntime.nodes.get('loop-2').active;
          window.personalBeforeTap=compositionRuntime.nodes.get('loop-3').item;
        }''')
        self.tap_panel(page, 'loop-3')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-3').item!==personalBeforeTap")
        self.settled(page)
        result = self.report(page, 'partial-personal-next-tap')
        self.assertTrue(page.evaluate("compositionRuntime.nodes.get('loop-2').active===foreignResident"))
        self.assertEqual(result['actual'][1]['name'], self.ids[1])
        self.assert_plan_matches_residents(result)

    def test_newer_panel_intent_supersedes_blocked_settlement_compilation(self):
        page = self.ready()
        self.defer(page, 'loop-1')
        page.evaluate('window.holdSettlementRecovery=true')
        self.tap_panel(page, 'loop-1')
        page.wait_for_function('''() => settlementHeldCompilers.length === 1 ||
          (compositionRuntime.events.some(e=>e.type==='handoff-deferred') &&
           !compositionRuntime.draining && !settlementCompilers.size)''', timeout=15000)
        if not page.evaluate('settlementHeldCompilers.length'):
            # Historical Studio never compiles its retained residents. Report
            # that observable mismatch, rather than treating a timeout as RED.
            self.assert_plan_matches_residents(self.report(page, 'superseding-no-settlement'))
            self.fail('the actual resident correction was not delivered through the compiler')
        correction = page.evaluate('settlementHeldCompilers[0].input.sources.map(s=>s.sha256)')
        self.assertEqual(correction, page.evaluate('settlementBefore.plan.sources.map(s=>s.sha256)'))
        page.evaluate('''() => {
          restoreSettlementFault();
          window.settlementSupersedeAfterDelivery='loop-2';
          settlementHeldCompilers.shift().send();
        }''')
        page.wait_for_function('() => window.settlementSuperseded && settlementHeldCompilers.length >= 1', timeout=15000)
        expected = page.evaluate('settlementHeldCompilers.at(-1).input.sources.map(s=>s.sha256)')
        self.assertNotEqual(expected, correction)
        page.evaluate('releaseSettlementCompilers()')
        self.settled(page)
        actual = page.evaluate('() => [...compositionRuntime.nodes.values()].map(n=>n.item.sha256)')
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / 'superseding-intent-before-export.json').write_text(json.dumps(dict(
            expected=expected, actual=actual, snapshot=self.snapshot(page)), indent=2) + '\n')
        # A stale publication may itself strand later exports. Diagnose the
        # wrong resident intent before asking that potentially pending API.
        self.assertEqual(actual, expected)
        result = self.report(page, 'superseding-intent')
        self.assertEqual([item['sha'] for item in result['actual']], expected)
        self.assert_plan_matches_residents(result)
        self.assertTrue(result['context'] and result['clock'] and result['generation'])
        self.assertIsNone(result['failure'])

    def test_export_requested_during_pending_handoff_waits_for_latest_intent(self):
        page = self.ready()
        self.defer(page, 'loop-1')
        self.tap_panel(page, 'loop-1')
        page.wait_for_function('() => settlementFault.applied')
        resolved = page.evaluate('''async () => {
          window.settlementExportResolved=false;
          window.settlementExport=compositionIO.plan().then(plan=>{
            window.settlementExportResolved=true; window.settlementExportPlan=plan; return plan;
          });
          await Promise.resolve();
          return settlementExportResolved;
        }''')
        self.assertFalse(resolved, 'export exposed a requested plan before its media handoff settled')
        page.evaluate('restoreSettlementFault()')
        self.tap_panel(page, 'loop-2')
        self.settled(page)
        page.evaluate('settlementExport')
        result = self.report(page, 'export-pending-latest')
        delivered = page.evaluate('settlementExportPlan.sources.map(s=>s.sha256)')
        self.assertEqual(delivered, [item['sha'] for item in result['actual']])
        self.assert_plan_matches_residents(result)

    def test_export_source_objects_keep_bytes_and_type_after_later_selection(self):
        page = self.ready()
        old = page.evaluate('''async () => {
          window.settlementExportPlan=await compositionIO.plan();
          return settlementExportPlan.sources.map(s=>({id:s.id,sha:s.sha256,bytes:s.bytes}));
        }''')
        self.tap_panel(page, 'loop-1')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-1').item!==settlementBefore.residents[0].item")
        self.settled(page)
        exported = page.evaluate('''async () => {
          const out=[];
          for(const source of settlementExportPlan.sources) {
            try {
              const bytes=await compositionIO.bytes(source);
              const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
                byte=>byte.toString(16).padStart(2,'0')).join('');
              out.push({id:source.id,sha,bytes:bytes.byteLength,type:compositionIO.type(source)});
            } catch(error) {out.push({id:source.id,error:String(error)});}
          }
          return out;
        }''')
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / 'export-source-lifetime.json').write_text(json.dumps(dict(expected=old, actual=exported), indent=2) + '\n')
        self.assertEqual(exported, [{**source, 'type': 'video/mp4'} for source in old])

    def test_request_c_a_keeps_a_in_its_slot_when_new_c_defers(self):
        page = self.ready(count=2, site='settlement-three')
        self.defer(page, 'loop-2')
        # With exactly A/B/C available, the first tap requests C/B and the
        # second requests C/A. Keep A in its own slot and prepare C in slot two.
        page.evaluate('''() => {
          for(const id of ['loop-1','loop-2'])
            document.querySelector(`#stage .loop[data-loop-id="${id}"]`).click();
        }''')
        self.wait_deferred(page)
        result = self.report(page, 'normalize-c-a')
        self.assertEqual(result['faultItem'], self.ids[2])
        self.assertEqual([item['name'] for item in result['actual']], self.ids[:2])
        self.assertTrue(all(row['sameMedia'] and row['sameAudio'] for row in result['residents']))
        self.assert_plan_matches_residents(result)
        self.assertEqual(result['mix'], 's0.1')
        self.assertEqual(len({item['sha'] for item in result['actual']}), 2)

    def test_request_b_c_keeps_b_in_its_slot_when_new_c_defers(self):
        page = self.ready(count=2, site='settlement-three')
        self.defer(page, 'loop-1')
        page.evaluate('''() => {
          for(const id of ['loop-2','loop-1'])
            document.querySelector(`#stage .loop[data-loop-id="${id}"]`).click();
        }''')
        self.wait_deferred(page)
        result = self.report(page, 'normalize-b-c')
        self.assertEqual(result['faultItem'], self.ids[2])
        self.assertEqual([item['name'] for item in result['actual']], self.ids[:2])
        self.assertTrue(all(row['sameMedia'] and row['sameAudio'] for row in result['residents']))
        self.assert_plan_matches_residents(result)
        self.assertEqual(result['mix'], 's0.1')

    def test_pure_permutation_keeps_both_resident_media_and_audio(self):
        page = self.ready(count=2, site='settlement-three')
        page.evaluate('''() => {
          for(const id of ['loop-1','loop-2','loop-1'])
            document.querySelector(`#stage .loop[data-loop-id="${id}"]`).click();
        }''')
        self.settled(page)
        result = self.report(page, 'normalize-permutation')
        self.assertEqual([item['name'] for item in result['actual']], self.ids[:2])
        for row in result['residents']:
            self.assertTrue(all(row[key] for key in ('sameNode', 'sameMedia', 'sameDeck', 'sameItem',
                'sameBirth', 'sameAudio', 'sameURL')), row)
        self.assert_plan_matches_residents(result)
        self.assertEqual(result['mix'], 's0.1')

    def test_resize_does_not_move_a_retiring_resident_into_a_surviving_slot(self):
        page = self.ready(count=3, site='settlement-three')
        page.evaluate('''() => {
          document.querySelector('#fewer').click();
          for(const id of ['loop-1','loop-2'])
            document.querySelector(`#stage .loop[data-loop-id="${id}"]`).click();
        }''')
        self.settled(page)
        result = self.report(page, 'normalize-resize')
        self.assertEqual([item['name'] for item in result['actual']], self.ids[:2])
        self.assertTrue(result['residents'][0]['sameMedia'] and result['residents'][0]['sameAudio'])
        self.assertTrue(result['residents'][1]['sameMedia'] and result['residents'][1]['sameAudio'])
        self.assertTrue(page.evaluate("() => !compositionRuntime.nodes.has('loop-3') && settlementBefore.residents[2].media.paused"))
        self.assert_plan_matches_residents(result)
        self.assertEqual(result['mix'], 's0.1')

    def test_failed_compile_releases_pending_export_to_existing_accepted_residents(self):
        page = self.ready()
        page.evaluate('window.settlementFailNextCompilation=true')
        self.tap_panel(page, 'loop-1')
        page.wait_for_function('() => settlementHeldCompilers.length === 1')
        resolved = page.evaluate('''async () => {
          window.settlementCompileExportResolved=false;
          window.settlementCompileExport=compositionIO.plan().then(plan=>{
            window.settlementCompileExportResolved=true;window.settlementCompileExportPlan=plan;return plan;
          });
          await Promise.resolve(); return settlementCompileExportResolved;
        }''')
        self.assertFalse(resolved)
        page.evaluate('releaseSettlementCompilers()')
        page.wait_for_function('''() => !settlementCompilers.size &&
          SimvltaneaStudio.snapshot().toastShown && SimvltaneaStudio.snapshot().toast.includes('duration')''')
        self.settled(page)
        resolved = page.evaluate('settlementCompileExportResolved')
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / 'failed-compile-waiter.json').write_text(json.dumps(dict(resolved=resolved,
            snapshot=self.snapshot(page)), indent=2) + '\n')
        self.assertTrue(resolved, 'owned compile failure stranded a pending export despite a healthy accepted session')
        self.assertEqual(page.evaluate('settlementCompileExportPlan.sources.map(s=>s.sha256)'),
                         page.evaluate('settlementBefore.plan.sources.map(s=>s.sha256)'))
        self.assert_plan_matches_residents(self.report(page, 'failed-compile-accepted'))

    def prepare_failed_repair(self, page):
        page.evaluate('''async () => {
          window.beforeRepairExport=await compositionIO.plan();
          window.settlementFailRecoveryCompilation=true;
          window.holdSettlementRecovery=true;
        }''')
        self.defer(page, 'loop-2')
        self.edit_two_new_panels(page)
        page.wait_for_function('''() => settlementHeldCompilers.length === 1 &&
          compositionRuntime.events.some(e=>e.type==='handoff-deferred')''')
        actual = page.evaluate('''() => [...compositionRuntime.nodes.values()].map(n=>n.item.sha256)''')
        before = page.evaluate('beforeRepairExport.sources.map(s=>s.sha256)')
        self.assertNotEqual(actual[0], before[0], 'slot one must commit before the repair compiler fails')
        self.assertEqual(actual[1:], before[1:])
        resolved = page.evaluate('''async () => {
          window.repairExportOutcome=null;
          window.repairExport=compositionIO.plan().then(plan=>{
            window.repairExportPlan=plan;
            return repairExportOutcome={kind:'resolved',shas:plan.sources.map(s=>s.sha256)};
          },error=>repairExportOutcome={kind:'rejected',name:error.name,message:error.message});
          await Promise.resolve();return repairExportOutcome;
        }''')
        self.assertIsNone(resolved)
        return actual, before

    def test_failed_repair_rejects_current_metadata_and_preserves_issued_source_bytes(self):
        page = self.ready()
        actual, before = self.prepare_failed_repair(page)
        page.evaluate('releaseSettlementCompilers()')
        page.wait_for_function('''() => !settlementCompilers.size &&
          SimvltaneaStudio.snapshot().toastShown && SimvltaneaStudio.snapshot().toast.includes('duration')''')
        self.settled(page)
        outcome = page.evaluate('repairExport')
        current = page.evaluate('''() => compositionIO.plan().then(
          plan=>({kind:'resolved',shas:plan.sources.map(s=>s.sha256)}),
          error=>({kind:'rejected',name:error.name,message:error.message}))''')
        old_asset = page.evaluate('''async () => {
          const source=beforeRepairExport.sources[0], bytes=await compositionIO.bytes(source);
          return {sha:Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),
            b=>b.toString(16).padStart(2,'0')).join(''),type:compositionIO.type(source),bytes:bytes.byteLength,
            expectedBytes:source.bytes};
        }''')
        PROOFS.mkdir(parents=True, exist_ok=True)
        (PROOFS / 'failed-repair-metadata.json').write_text(json.dumps(dict(actual=actual,
            previous=before,waiting=outcome,current=current,oldAsset=old_asset), indent=2) + '\n')
        self.assertEqual(old_asset['sha'], before[0])
        self.assertEqual(old_asset['bytes'], old_asset['expectedBytes'])
        self.assertEqual(old_asset['type'], 'video/mp4')
        self.assertEqual(outcome['kind'], 'rejected', 'failed repair exported the previous, no-longer-resident cohort')
        self.assertEqual(current['kind'], 'rejected', 'current export falsely claims metadata describes the resident cohort')

    def test_newer_intent_is_not_rejected_by_an_older_repair_compiler_error(self):
        page = self.ready()
        self.prepare_failed_repair(page)
        page.evaluate('''() => {
          restoreSettlementFault();
          window.settlementSupersedeAfterDelivery='loop-3';
          settlementHeldCompilers.shift().send();
        }''')
        page.wait_for_function('() => window.settlementSuperseded && settlementHeldCompilers.length >= 1')
        self.assertIsNone(page.evaluate('repairExportOutcome'), 'an older failure settled a newer intent\'s export')
        page.evaluate('releaseSettlementCompilers()')
        self.settled(page)
        outcome = page.evaluate('repairExport')
        result = self.report(page, 'newer-intent-after-repair-error')
        self.assertEqual(outcome['kind'], 'resolved')
        self.assertEqual(outcome['shas'], [item['sha'] for item in result['actual']])
        self.assert_plan_matches_residents(result)


if __name__ == '__main__':
    unittest.main()
