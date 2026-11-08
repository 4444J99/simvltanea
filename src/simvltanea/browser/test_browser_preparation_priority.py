"""Urgent decoder repair can yield hidden preparation without touching residents."""
from __future__ import annotations

import unittest

from simvltanea.browser import test_browser_native_rescue as fixture


class PreparationPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.NativeRescueTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.NativeRescueTests.tearDownClass.__func__(cls)

    open = fixture.NativeRescueTests.open
    freeze = fixture.NativeRescueTests.freeze

    def park_ordinary(self, page):
        page.evaluate('''() => {
          live.crossfadeSec=.2;
          items.push({...items[1],name:'ordinary',sha256:'5'.repeat(64)});
          window.ordinaryNode=live.nodes.get('loop-2');window.ordinaryOutgoing=ordinaryNode.active;
          window.ordinaryUrl=ordinaryOutgoing.url;window.ordinaryBirth=ordinaryNode.birthTime;
          window.ordinaryIncoming=ordinaryNode.decks.find(deck=>deck!==ordinaryOutgoing);
          window.maxPopulated=4;
          const prime=live.prime.bind(live);
          live.prime=(...args)=>{
            maxPopulated=Math.max(maxPopulated,[...live.slots.values()].flatMap(n=>n.decks).filter(d=>d.url).length);
            return prime(...args);
          };
          const current=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'currentTime');
          for(const row of neighbors)Object.defineProperty(row.media,'currentTime',{configurable:true,
            get:()=>current.get.call(row.media),set:value=>{neighborCalls.push([row.node.id,'seek']);
              current.set.call(row.media,value)}});
          window.seamVisits=0;
          const seam=live.waitForSeam.bind(live);
          live.waitForSeam=(n,signal)=>{
            if(n!==ordinaryNode || ++seamVisits!==1)return seam(n,signal);
            window.parked=true;
            return new Promise((resolve,reject)=>{
              window.releasePark=resolve;
              signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
            });
          };
          window.order=[];window.atRescueCommit=null;
          const record=live.record.bind(live);
          live.record=(type,id,detail)=>{
            if(type==='resource-retired' || type==='native-loop-rescue-started' ||
                type==='native-loop-rescue-committed' || type==='resident')order.push({type,id,...detail});
            if(type==='native-loop-rescue-committed')atRescueCommit={
              ordinarySame:ordinaryNode.active===ordinaryOutgoing && ordinaryOutgoing.url===ordinaryUrl &&
                ordinaryNode.birthTime===ordinaryBirth,
              neighborsSame:neighbors.every(row=>row.node.active===row.deck && row.deck.url===row.url &&
                row.node.audio===row.binding && row.node.callbacks>row.frames),
              calls:neighborCalls.slice(),standbys:live.activeStandbys,
              populated:[...live.slots.values()].flatMap(n=>n.decks).filter(d=>d.url).length};
            return record(type,id,detail);
          };
          window.ordinaryChange=live.reconcile({plan:planFor([0,4,2,3]),
            items:[items[0],items[4],items[2],items[3]],playing:true,atLoopBoundary:true});
        }''')
        page.wait_for_function('window.parked && ordinaryNode.phase==="READY" && ordinaryIncoming.media.paused')

    def test_parked_hidden_successor_yields_before_rescue_and_retries_same_intent(self):
        page = self.open()
        self.park_ordinary(page)
        self.freeze(page)
        page.wait_for_timeout(1000)
        self.assertTrue(page.evaluate('node.active!==outgoing'),
                        'a parked ordinary successor prevented the urgent failed-seek repair from starting')
        self.assertTrue(page.evaluate('ordinaryChange'), 'yield discarded the still-current ordinary intent')
        result = page.evaluate('''() => ({atRescueCommit,order,seamVisits,
          final:ordinaryNode.item===items[4] && node.item===residentBefore.item &&
            node.birthTime===residentBefore.birth,
          maxPopulated,maxPermit:live.maxConcurrentStandbys,permit:live.activeStandbys,
          retired:live.proofRetired.find(row=>row.url===before.url)})''')
        self.assertTrue(result['atRescueCommit']['ordinarySame'] and result['final'])
        self.assertTrue(result['atRescueCommit']['neighborsSame'])
        self.assertEqual(result['atRescueCommit']['calls'], [])
        self.assertEqual(result['atRescueCommit']['standbys'], 1)
        self.assertLessEqual(result['atRescueCommit']['populated'], 5)
        self.assertEqual(result['maxPopulated'], 5)
        self.assertEqual((result['maxPermit'], result['permit']), (1, 0))
        self.assertEqual(result['seamVisits'], 2)
        self.assertLess(result['retired']['maxGapMs'], 2000)
        retired = next(i for i, row in enumerate(result['order'])
                       if row['type'] == 'resource-retired' and row['id'] == 'loop-2')
        started = next(i for i, row in enumerate(result['order'])
                       if row['type'] == 'native-loop-rescue-started')
        self.assertLess(retired, started, 'the permit transferred before hidden-source cleanup')

    def test_urgent_fifo_precedes_normal_queue_and_cancelled_jobs_never_run(self):
        page = self.open()
        page.evaluate('''() => {
          window.visits=[];window.unknownReleased=false;
          window.unknown=live.withPreparation(()=>new Promise(resolve=>{window.releaseUnknown=resolve}));
          const job=(label,options)=>live.withPreparation(()=>{visits.push(label)},options);
          window.normalA=job('normal-a');
          window.urgentA=job('urgent-a',{urgent:true});
          const cancelled=new AbortController();
          window.cancelledJob=job('cancelled',{urgent:true,signal:cancelled.signal}).catch(e=>e.name);
          window.urgentB=job('urgent-b',{urgent:true});
          window.normalB=job('normal-b');cancelled.abort();
        }''')
        page.wait_for_timeout(100)
        self.assertEqual(page.evaluate('visits'), [], 'an unknown permit owner was preempted')
        self.assertEqual(page.evaluate('live.activeStandbys'), 1)
        page.evaluate('releaseUnknown();Promise.all([unknown,normalA,urgentA,cancelledJob,urgentB,normalB])')
        self.assertEqual(page.evaluate('visits'), ['urgent-a', 'urgent-b', 'normal-a', 'normal-b'])
        self.assertEqual(page.evaluate('cancelledJob'), 'AbortError')
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_visible_ordinary_fade_keeps_its_permit_until_verified_commit(self):
        page = self.open()
        page.evaluate('''() => {
          live.crossfadeSec=5;
          items.push({...items[1],name:'ordinary',sha256:'5'.repeat(64)});
          window.ordinaryNode=live.nodes.get('loop-2');
          window.ordinaryChange=setClips([0,4,2,3]);
        }''')
        page.wait_for_function('live.fade?.node===ordinaryNode && live.fade.incoming.weight>0')
        self.freeze(page)
        page.wait_for_function('Boolean(node.nativeRescue)')
        self.assertTrue(page.evaluate('''live.fade?.node===ordinaryNode && !incoming.url &&
          live.activeStandbys===1 && !live.events.some(e=>e.type==='preparation-yielded')'''),
                        'urgent work preempted a successor already visible in its ordinary fade')
        page.evaluate('live.fade.duration=.2;ordinaryChange')
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        self.assertTrue(page.evaluate('ordinaryNode.item===items[4] && node.item===residentBefore.item'))
        self.assertEqual(page.evaluate('neighborCalls.filter(row=>row[0]!=="loop-2")'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def hold_rescue_prime(self, page):
        page.evaluate('''() => {
          const prime=live.prime.bind(live);
          live.prime=async(deck,n,signal)=>{
            await prime(deck,n,signal);
            if(n===node && n.nativeRescue){
              window.rescueHeld=true;
              await new Promise((resolve,reject)=>{
                window.releaseRescue=resolve;
                signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
              });
            }
          };
        }''')

    def test_supersession_cancels_a_yielded_retry_without_cancelling_sibling_rescue(self):
        page = self.open()
        self.park_ordinary(page)
        self.hold_rescue_prime(page)
        self.freeze(page)
        page.wait_for_function('window.rescueHeld && !ordinaryIncoming.url')
        self.assertTrue(page.evaluate('setClips([0,1,2,3])'))
        self.assertFalse(page.evaluate('ordinaryChange'))
        page.evaluate('releaseRescue()')
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        self.assertTrue(page.evaluate('''ordinaryNode.active===ordinaryOutgoing && ordinaryNode.item===items[1] &&
          ordinaryOutgoing.url===ordinaryUrl && ordinaryNode.birthTime===ordinaryBirth && seamVisits===1'''))
        self.assertEqual(page.evaluate('neighborCalls'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_source_epoch_change_invalidates_a_yielded_retry_before_reload(self):
        page = self.open()
        self.park_ordinary(page)
        self.hold_rescue_prime(page)
        self.freeze(page)
        page.wait_for_function('window.rescueHeld && !ordinaryIncoming.url')
        page.evaluate('ordinaryOutgoing.sourceEpoch++;releaseRescue()')
        self.assertFalse(page.evaluate('ordinaryChange'))
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        self.assertTrue(page.evaluate('''ordinaryNode.active===ordinaryOutgoing && ordinaryNode.item===items[1] &&
          !ordinaryIncoming.url && seamVisits===1'''))
        self.assertEqual(page.evaluate('neighborCalls'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_cancelled_urgent_request_allows_the_yielded_ordinary_intent_to_retry(self):
        page = self.open()
        self.park_ordinary(page)
        page.evaluate('''() => {
          window.urgentRan=false;const controller=new AbortController();
          window.urgent=live.withPreparation(()=>{urgentRan=true},
            {urgent:true,signal:controller.signal}).catch(e=>e.name);
          controller.abort();
        }''')
        self.assertEqual(page.evaluate('urgent'), 'AbortError')
        self.assertTrue(page.evaluate('ordinaryChange'))
        self.assertTrue(page.evaluate('''!urgentRan && ordinaryNode.item===items[4] &&
          node.active===outgoing && node.item===residentBefore.item && seamVisits===2'''))
        self.assertEqual(page.evaluate('neighborCalls.filter(row=>row[0]!=="loop-2")'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_hidden_prime_cancels_locally_and_cleans_up_before_urgent_admission(self):
        page = self.open()
        page.evaluate('''() => {
          live.crossfadeSec=.2;
          items.push({...items[1],name:'ordinary',sha256:'5'.repeat(64)});
          window.ordinaryNode=live.nodes.get('loop-2');window.ordinaryOutgoing=ordinaryNode.active;
          window.ordinaryIncoming=ordinaryNode.decks.find(d=>d!==ordinaryOutgoing);
          let held=false;const prime=live.prime.bind(live);
          live.prime=async(deck,n,signal)=>{
            await prime(deck,n,signal);
            if(n===ordinaryNode && !held){held=true;window.primingHeld=true;
              await new Promise((_,reject)=>signal.addEventListener('abort',
                ()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
            }
            if(n===node && n.nativeRescue)window.cleanAtStart=!ordinaryIncoming.url &&
              ordinaryNode.active===ordinaryOutgoing && neighborCalls.length===0;
          };
          window.ordinaryChange=setClips([0,4,2,3]);
        }''')
        page.wait_for_function('window.primingHeld && ordinaryNode.phase==="PRIMING"')
        self.freeze(page)
        page.wait_for_function('node.active!==outgoing && !node.nativeRescue')
        self.assertTrue(page.evaluate('ordinaryChange'))
        self.assertTrue(page.evaluate('window.cleanAtStart && ordinaryNode.item===items[4]'))
        self.assertEqual(page.evaluate('neighborCalls.filter(row=>row[0]!=="loop-2")'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_an_active_urgent_owner_is_not_preempted_by_another_urgent_job(self):
        page = self.open()
        page.evaluate('''() => {
          window.yieldCalls=0;window.secondRan=false;
          window.first=live.withPreparation(()=>new Promise(resolve=>{window.releaseFirst=resolve}),
            {urgent:true,onYield:()=>{yieldCalls++;return true}});
          window.second=live.withPreparation(()=>{secondRan=true},{urgent:true});
        }''')
        page.wait_for_timeout(100)
        self.assertTrue(page.evaluate('yieldCalls===0 && !secondRan && live.activeStandbys===1'))
        page.evaluate('releaseFirst();Promise.all([first,second])')
        self.assertTrue(page.evaluate('secondRan && yieldCalls===0'))
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_queued_ordinary_intent_survives_verified_rescue_of_its_same_resident(self):
        page = self.open()
        page.evaluate('''() => {
          live.crossfadeSec=.2;
          // The native fault belongs to the original source. The later
          // ordinary successor reuses this element, after rescue retires it.
          const unload=live.unload.bind(live);
          live.unload=deck=>{
            const failedSource=deck.url===before.url;unload(deck);
            if(failedSource)for(const key of ['currentTime','paused','seeking','play'])delete deck.media[key];
          };
          window.blocker=live.withPreparation(()=>new Promise(resolve=>{window.releaseBlocker=resolve}));
          items.push({...items[0],name:'ordinary',sha256:'5'.repeat(64)});
          window.ordinaryChange=setClips([4,1,2,3]);
        }''')
        page.wait_for_function('typeof releaseBlocker==="function" && live.draining && !node.busy')
        self.freeze(page)
        page.wait_for_function('Boolean(node.nativeRescue)')
        page.evaluate('releaseBlocker()')
        accepted = page.evaluate('ordinaryChange')
        self.assertTrue(accepted, 'queued ordinary replacement failed: ' + str(page.evaluate('''({
          failure:live.lastFailure,events:live.events.filter(e=>e.type.includes('rescue') ||
            e.type==='handoff-deferred' || e.type==='resident')})''')))
        self.assertTrue(page.evaluate('''node.item===items[4] &&
          live.events.filter(e=>e.type==='native-loop-rescue-committed').length===1'''))
        self.assertEqual(page.evaluate('neighborCalls'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])

    def test_new_logical_residency_token_invalidates_a_queued_ordinary_intent(self):
        page = self.open()
        page.evaluate('''() => {
          window.blocker=live.withPreparation(()=>new Promise(resolve=>{window.releaseBlocker=resolve}));
          items.push({...items[0],name:'ordinary',sha256:'5'.repeat(64)});
          window.ordinaryChange=setClips([4,1,2,3]);
        }''')
        page.wait_for_function('typeof releaseBlocker==="function" && live.draining && !node.busy')
        page.evaluate('node.residentIdentity={};outgoing.residentIdentity=node.residentIdentity;releaseBlocker()')
        self.assertFalse(page.evaluate('ordinaryChange'),
                         'a new residency token was treated as a verified same-resident decoder repair')
        self.assertTrue(page.evaluate('node.active===outgoing && node.item===residentBefore.item && !incoming.url'))
        self.assertEqual(page.evaluate('neighborCalls'), [])
        self.assertEqual(page.evaluate('[live.activeStandbys,live.maxConcurrentStandbys]'), [0, 1])
