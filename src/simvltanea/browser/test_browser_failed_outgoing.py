"""Real media handoffs after a source-owned native loop-seek recovery fails."""
from __future__ import annotations

import base64
import unittest

from simvltanea.browser import test_browser_live as live_tests


class FailedOutgoingHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live_tests.PersistentSessionTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        live_tests.PersistentSessionTests.tearDownClass.__func__(cls)

    def open(self):
        context = self.browser.new_context(viewport={'width': 800, 'height': 500})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route('http://live.test/**', lambda route: route.fulfill(content_type='text/html', body=
                   '<main id="stage" style="position:relative;width:800px;height:500px"></main>'))
        page.goto('http://live.test/?proof=1')
        page.add_script_tag(path=str(live_tests.LIVE))
        payload = [base64.b64encode(self.fixtures[f'loop-{i}.mp4'].read_bytes()).decode()
                   for i in range(1, 5)]
        page.evaluate(r'''payload => {
          window.items=payload.map((encoded,i)=>({name:`clip-${i}`,sha256:String(i+1).padStart(64,'0'),
            file:new Blob([Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))],{type:'video/mp4'}),
            asset:{fps:30}}));
          window.planFor=indices=>({plan_version:1,frames:2880,fps:30,
            sources:indices.map((i,j)=>({id:`source-${j+1}`,sha256:items[i].sha256})),
            tracks:indices.map((_,i)=>({id:`loop-${i+1}`,spans:[{source:`source-${i+1}`}]}))});
          window.live=new SimvltaneaLive.Session(document.querySelector('#stage'),
            {crossfadeSec:1.2,primeTimeoutMs:2000});
          window.setClips=indices=>live.reconcile({plan:planFor(indices),items:indices.map(i=>items[i]),playing:true});
        }''', payload)
        page.evaluate('setClips([0,1])')
        page.evaluate('''() => document.addEventListener('click',()=>{
          window.unlocked=live.unlock();live.setSound({enabled:true,volume:.1});},{once:true})''')
        page.mouse.click(10, 10)
        page.evaluate('unlocked')
        page.evaluate('''() => {
          window.node=live.nodes.get('loop-1');window.outgoing=node.active;
          window.incoming=node.decks.find(deck=>deck!==outgoing);
          window.sibling=live.nodes.get('loop-2').active;
          window.before={url:outgoing.url,epoch:outgoing.sourceEpoch,binding:outgoing.binding,
            siblingUrl:sibling.url,siblingBinding:sibling.binding,siblingFrames:sibling.callbacks};
          window.residentCalls=[];
          for(const name of ['play','pause','load']) {
            const native=sibling.media[name].bind(sibling.media);
            sibling.media[name]=(...args)=>{residentCalls.push(name);return native(...args)};
          }
          window.fadeRows=[];
          live.clock.subscribe(()=>{if(live.fade)fadeRows.push({wall:performance.now(),
            duration:live.fade.duration,oldWeight:outgoing.weight,newWeight:incoming.weight,
            oldOpacity:Number(outgoing.media.style.opacity),newOpacity:Number(incoming.media.style.opacity),
            gains:outgoing.binding.target+incoming.binding.target,
            incomingChanges:incoming.progress.sourceChanges,
            incomingSeeking:incoming.media.seeking,incomingPaused:incoming.media.paused})});
        }''')
        return page

    def fail_native_seek(self, page):
        # The fault is confined to the outgoing HTMLVideoElement. Real decoded
        # frames establish the production guard's movement and end evidence;
        # neither the guard nor incoming freshness/promotion is replaced.
        page.wait_for_function('outgoing.loopSeek?.endSeen && !outgoing.media.seeking', timeout=5000)
        page.evaluate('''() => {
          const media=outgoing.media;HTMLMediaElement.prototype.pause.call(media);
          let current=0;
          Object.defineProperty(media,'currentTime',{configurable:true,get:()=>current,set:value=>{current=value}});
          Object.defineProperty(media,'paused',{configurable:true,get:()=>false});
          Object.defineProperty(media,'seeking',{configurable:true,get:()=>true});
          media.play=()=>Promise.resolve();
        }''')
        page.wait_for_function('Boolean(outgoing.loopSeek?.attempt)', timeout=3000)
        # Reproduce the native receipt's already-stale resident before the next
        # real source finishes priming, making an ordinary 1.2-second fade unsafe.
        page.wait_for_timeout(400)

    def test_failed_outgoing_retires_before_two_seconds_after_real_fresh_successor(self):
        page = self.open()
        self.fail_native_seek(page)
        self.assertTrue(page.evaluate('setClips([2,1])'))
        result = page.evaluate('''() => ({
          retired:live.proofRetired.find(item=>item.url===before.url),rows:fadeRows,
          active:node.active===incoming,source:node.item===items[2],permits:live.activeStandbys,
          siblingSame:live.nodes.get('loop-2').active===sibling && sibling.url===before.siblingUrl &&
            sibling.binding===before.siblingBinding,siblingFrames:sibling.callbacks-before.siblingFrames,
          calls:residentCalls,attempts:live.events.filter(event=>event.type==='native-loop-seek-recovery').length,
          recoveries:live.events.filter(event=>event.type==='native-loop-seek-recovered').length})''')
        self.assertLess(result['retired']['maxGapMs'], 2000,
                        'a verified moving successor retained the failed outgoing picture for a full normal fade')
        self.assertGreater(result['retired']['maxGapMs'], 950, 'the original decoded gap was reset')
        self.assertTrue(result['active'] and result['source'] and result['siblingSame'])
        self.assertEqual(result['permits'], 0)
        self.assertEqual(result['calls'], [])
        self.assertGreater(result['siblingFrames'], 20)
        self.assertEqual((result['attempts'], result['recoveries']), (1, 0))
        rows = result['rows']
        self.assertGreaterEqual(len(rows), 3)
        self.assertGreaterEqual(rows[0]['incomingChanges'], 2)
        self.assertTrue(all(not row['incomingSeeking'] and not row['incomingPaused'] for row in rows))
        self.assertTrue(all(row['oldOpacity'] == 1 for row in rows))
        self.assertTrue(all(abs(row['oldWeight'] + row['newWeight'] - 1) < 1e-8 for row in rows))
        self.assertTrue(all(abs(row['newOpacity'] - row['newWeight']) < 1e-8 for row in rows))
        self.assertTrue(all(abs(row['gains'] - 2 ** -.5) < 1e-8 for row in rows))
        self.assertTrue(all(a['newWeight'] <= b['newWeight'] for a, b in zip(rows, rows[1:])))
        self.assertGreater(sum(0 < row['newWeight'] < 1 for row in rows), 2)

    def test_healthy_outgoing_keeps_normal_crossfade(self):
        page = self.open()
        self.assertTrue(page.evaluate('setClips([2,1])'))
        rows = page.evaluate('fadeRows')
        self.assertGreater(rows[-1]['wall'] - rows[0]['wall'], 1000)
        self.assertTrue(all(row['duration'] == 1.2 for row in rows))

    def test_starved_incoming_is_never_revealed_after_outgoing_failure(self):
        page = self.open()
        self.fail_native_seek(page)
        page.evaluate('''() => {
          const prime=live.prime.bind(live);window.revealed=false;
          live.prime=async(...args)=>{await prime(...args);incoming.media.pause();incoming.media.play=()=>Promise.resolve()};
          new MutationObserver(()=>{if(Number(incoming.media.style.opacity)>0)revealed=true})
            .observe(incoming.media,{attributes:true,attributeFilter:['style']});
        }''')
        self.assertFalse(page.evaluate('setClips([2,1])'))
        self.assertFalse(page.evaluate('revealed'))
        self.assertTrue(page.evaluate('node.active===outgoing && outgoing.url===before.url'))
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertEqual(page.evaluate('fadeRows.length'), 0)

    def test_deliberate_pause_invalidates_failed_seek_shortcut(self):
        page = self.open()
        self.fail_native_seek(page)
        page.evaluate('live.pause()')
        self.assertTrue(page.evaluate('setClips([2,1])'))
        rows = page.evaluate('fadeRows')
        self.assertGreater(rows[-1]['wall'] - rows[0]['wall'], 1000)
        self.assertTrue(all(row['duration'] == 1.2 for row in rows))

    def test_actual_outgoing_progress_during_priming_prevents_stale_attempt_shortcut(self):
        page = self.open()
        self.fail_native_seek(page)
        page.evaluate('''() => {
          const prime=live.prime.bind(live);
          live.prime=async(...args)=>{
            await prime(...args);
            const media=outgoing.media;
            for(const key of ['currentTime','paused','seeking','play'])delete media[key];
            await media.play();
            await new Promise(resolve=>media.requestVideoFrameCallback(()=>media.requestVideoFrameCallback(resolve)));
            // A later transient seek must not reuse the old failed-attempt
            // diagnosis after distinct real frames recovered during priming.
            Object.defineProperty(media,'seeking',{configurable:true,get:()=>true});
          };
        }''')
        self.assertTrue(page.evaluate('setClips([2,1])'))
        rows = page.evaluate('fadeRows')
        self.assertGreater(rows[-1]['wall'] - rows[0]['wall'], 1000)
        self.assertTrue(all(row['duration'] == 1.2 for row in rows))

    def test_failed_promotion_after_short_fade_retains_outgoing_and_releases_permit(self):
        page = self.open()
        self.fail_native_seek(page)
        page.evaluate('''() => {
          const promote=live.playPromoted.bind(live);
          live.playPromoted=(deck,...args)=>{
            deck.media.pause();deck.media.play=()=>Promise.resolve();return promote(deck,...args);
          };
        }''')
        self.assertFalse(page.evaluate('setClips([2,1])'))
        self.assertTrue(page.evaluate('''node.active===outgoing && node.media===outgoing.media &&
          outgoing.url===before.url && outgoing.binding===before.binding && outgoing.weight===1'''))
        self.assertEqual(page.evaluate('incoming.url'), None)
        self.assertEqual(page.evaluate('live.activeStandbys'), 0)
        self.assertTrue(page.evaluate('fadeRows.length>2 && fadeRows.every(row=>row.duration===.2)'))
        self.assertEqual(page.evaluate('residentCalls'), [])
