"""Library prefetch must not allocate a temporary native metadata decoder."""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import unittest

from simvltanea.browser import test_browser_studio as studio_tests


MEDIA_PROBE_OBSERVER = r'''(() => {
  const play = HTMLMediaElement.prototype.play;
  window.metadataPlays = [];
  HTMLMediaElement.prototype.play = function(...args) {
    if (this instanceof HTMLVideoElement && this.src.startsWith('blob:') && !this.dataset.loopId) {
      const observation = {url:this.src, permit:window.compositionRuntime?.activeStandbys,
        decoded:false};
      this.addEventListener('loadeddata', () => { observation.decoded = true; }, {once:true});
      metadataPlays.push(observation);
    }
    return play.apply(this, args);
  };
})();'''


class LibraryPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        studio_tests.StudioLibraryTests.setUpClass.__func__(cls)
        # Keep valid MP4/codec metadata but destroy encoded media packets. The
        # manifest and digest honestly describe these unplayable bytes, so only
        # real deck admission can reject the decode failure.
        source = cls.by_id[cls.ids[0]]
        content = bytearray((studio_tests.LIBRARY / source['file']).read_bytes())
        cursor = 0
        while cursor < len(content):
            size, kind = struct.unpack_from('>I4s', content, cursor)
            if size < 8:
                raise AssertionError('unexpected MP4 box in synthetic fixture')
            if kind == b'mdat':
                content[cursor + 8:cursor + size] = bytes(size - 8)
                break
            cursor += size
        else:
            raise AssertionError('synthetic MP4 has no media packets')
        cls.undecodable_id = hashlib.sha256(content).hexdigest()[:12]
        bad = {**source, 'id': cls.undecodable_id, 'file': f'clips/{cls.undecodable_id}.mp4'}
        site = studio_tests.LIBRARY_SITES / 'prefetch-undecodable'
        shutil.copytree(studio_tests.LIBRARY_SITES / 'good', site)
        (site / 'library' / bad['file']).write_bytes(content)
        manifest = {'schema': cls.manifest['schema'],
                    'clips': [cls.by_id[clip_id] for clip_id in cls.ids[:4]] + [bad]}
        (site / 'library' / 'manifest.json').write_text(json.dumps(manifest))
        order = sorted(clip['id'] for clip in manifest['clips'])
        cls.undecodable_mix = '.'.join(str(order.index(clip_id)) for clip_id in cls.ids[:4])

    @classmethod
    def tearDownClass(cls):
        studio_tests.StudioLibraryTests.tearDownClass.__func__(cls)

    open = studio_tests.StudioLibraryTests.open
    snapshot = studio_tests.StudioLibraryTests.snapshot
    showing = studio_tests.StudioLibraryTests.showing
    playing = studio_tests.StudioLibraryTests.playing
    prefetched = studio_tests.StudioLibraryTests.prefetched
    settled = studio_tests.StudioLibraryTests.settled
    unlock = studio_tests.StudioLibraryTests.unlock
    tap = studio_tests.StudioLibraryTests.tap

    def test_library_prefetch_keeps_decoder_work_inside_persistent_slots(self):
        # Fix only the next-roll seed so the spare-prefetch assertion is repeatable.
        script = MEDIA_PROBE_OBSERVER + '''(() => {
          const random=crypto.getRandomValues.bind(crypto);
          crypto.getRandomValues=values=>{
            if(values instanceof Uint32Array && values.length===1){values[0]=37;return values;}
            return random(values);
          };
        })();'''
        page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0&proof=1', has_touch=True,
                         init_script=script)
        self.showing(page, self.ids[:4])
        library = self.prefetched(page)
        self.assertGreater(len(library['cached']), 4, 'no spare asset was actually prefetched')
        self.assertEqual(page.evaluate('metadataPlays'), [],
                         'library prefetch acquired the live permit and played an extra metadata decoder')
        frames = page.evaluate('[...compositionRuntime.nodes.values()].map(n=>n.active.progress.sourceChanges)')
        page.wait_for_function('before=>[...compositionRuntime.nodes.values()].every((n,i)=>'
                               'n.active.progress.sourceChanges>before[i]+2)', arg=frames)
        self.assertEqual(page.evaluate('compositionRuntime.maxConcurrentStandbys'), 1)

    def test_personal_upload_still_decodes_its_metadata_before_admission(self):
        page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0&proof=1', has_touch=True,
                         init_script=MEDIA_PROBE_OBSERVER)
        self.showing(page, self.ids[:4])
        self.prefetched(page)
        page.evaluate('metadataPlays.length=0')
        clip = self.by_id[self.ids[0]]
        page.set_input_files('#files', dict(name='personal.mp4', mimeType='video/mp4',
                                            buffer=(studio_tests.LIBRARY / clip['file']).read_bytes()))
        page.wait_for_function("() => SimvltaneaStudio.snapshot().source==='own' && !SimvltaneaStudio.snapshot().busy")
        self.playing(page, 1)
        probes = page.evaluate('metadataPlays')
        self.assertTrue(probes and all(p['decoded'] and p['permit'] == 1 for p in probes), probes)
        self.assertEqual(self.snapshot(page)['loops'][0]['width'], clip['width'])
        self.assertEqual(self.snapshot(page)['loops'][0]['height'], clip['height'])

    def test_hash_consistent_decode_failure_keeps_existing_residents(self):
        page = self.open(site='prefetch-undecodable',
                         query=f'?seed=99&mix=s{self.undecodable_mix}&evolve=0&proof=1', has_touch=True,
                         init_script=MEDIA_PROBE_OBSERVER)
        self.showing(page, self.ids[:4])
        self.unlock(page)
        page.evaluate('''() => {
          window.retainedResidents=[...compositionRuntime.nodes.values()].map(n=>({node:n,media:n.media,item:n.item,
            url:n.active.url,frames:n.active.progress.sourceChanges}));
        }''')
        self.tap(page, '.loop[data-loop-id="loop-1"]')
        page.wait_for_function('''() => compositionRuntime.lastFailure && !compositionRuntime.draining &&
          [...compositionRuntime.nodes.values()].every(n=>!n.busy)''')
        self.assertIn(self.undecodable_id, self.snapshot(page)['library']['cached'])
        self.assertTrue(page.evaluate('''() => retainedResidents.every(({node,media,item,url})=>
          compositionRuntime.nodes.get(node.id)===node && node.media===media && node.item===item &&
          node.active.url===url && !node.media.error && !node.media.paused)'''))
        page.wait_for_function('''() => retainedResidents.every(({node,frames})=>
          node.active.progress.sourceChanges>frames+2)''')
        self.assertTrue(page.evaluate('''() => [...compositionRuntime.nodes.values()].every(n=>
          n.decks.filter(d=>d.url).length===1) && compositionRuntime.activeStandbys===0'''))
        self.assertEqual(page.evaluate('metadataPlays'), [])

    def test_library_integrity_refusals_still_exclude_bad_bytes(self):
        for fault in ('size', 'digest'):
            with self.subTest(fault=fault):
                script = MEDIA_PROBE_OBSERVER + '''(() => {
                  const nativeFetch=fetch;
                  window.fetch=async(...args)=>{
                    const response=await nativeFetch(...args);
                    if(!String(args[0]).endsWith('/clips/TARGET.mp4'))return response;
                    const data=new Uint8Array(await response.arrayBuffer());
                    if('FAULT'==='size')return new Response(data.slice(1),{status:200});
                    data[data.length-1]^=1;return new Response(data,{status:200});
                  };
                })();'''.replace('TARGET', self.ids[0]).replace('FAULT', fault)
                page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0', init_script=script)
                page.wait_for_function('''() => SimvltaneaStudio.snapshot().library.broken===1 &&
                  compositionRuntime.ready && !compositionRuntime.draining''')
                self.assertNotIn(self.ids[0], self.snapshot(page)['selection'])
                self.assertNotIn(self.ids[0], self.snapshot(page)['library']['cached'])
                self.playing(page, 4)
                self.assertEqual(page.evaluate('metadataPlays'), [])
                page.close()

    def test_library_codec_refusal_still_precedes_decoder_admission(self):
        script = MEDIA_PROBE_OBSERVER + '''(() => {
          const support=HTMLMediaElement.prototype.canPlayType;
          HTMLMediaElement.prototype.canPlayType=function(type){
            return type.startsWith('video/mp4') ? '' : support.call(this,type);
          };
        })();'''
        page = self.open(query='?seed=99&mix=s0.1.2.3&evolve=0', init_script=script)
        page.wait_for_function("() => SimvltaneaStudio.snapshot().source==='builtin'")
        self.playing(page, self.snapshot(page)['panels'])
        self.assertEqual(page.evaluate('metadataPlays'), [])
