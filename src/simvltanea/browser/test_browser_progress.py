"""Proof-only decoded-frame accounting; no synthetic media playback policy."""
from pathlib import Path
import subprocess
import unittest

LIVE = Path(__file__).with_name('browser.live.js')


class FrameProgressTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');\n"
                        "const {FrameProgress,Session}=require(process.argv[1]);\n" + body,
                        str(LIVE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_loop_alias_records_intermediate_changes_and_ignores_repeats(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);
p.observe(0,0);p.observe(400,.4);p.observe(800,0);
let s=p.snapshot(800,true);assert.equal(s.changes,3);assert.equal(s.mediaTime,0);
assert.equal(s.maxGapMs,400);assert.deepEqual(s.trace.map(x=>x.mediaTime),[0,.4,0]);
p.observe(1000,0);p.observe(1500,0);p.observe(3000,0);
s=p.snapshot(3000);assert.equal(s.changes,3);assert.equal(s.currentGapMs,2200);
assert.equal(s.maxGapMs,2200);assert.equal(s.lifetimeMaxGapMs,2200);
''')

    def test_hidden_stall_is_retained_after_recovery_and_retirement(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);
p.observe(0,0);p.observe(2400,.1);p.observe(2433,.2);
assert.equal(p.snapshot(2450).maxGapMs,2400);
p.retire(2466);assert.equal(p.snapshot(6000).maxGapMs,2400);
p.assign('blob:b',6000);p.observe(6100,0);p.setForeground(true,6200,true);
p.observe(6233,.1);const s=p.snapshot(6250,true);
assert.equal(s.epoch,2);assert.equal(s.changes,5);assert.equal(s.sourceChanges,2);
assert.equal(s.maxGapMs,33);assert.equal(s.lifetimeMaxGapMs,2400);
assert.equal(s.url,'blob:b');assert.deepEqual(s.trace.map(x=>x.wall),[6100,6233]);
''')

    def test_pending_and_standby_time_do_not_count_until_reveal(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.observe(0,0);p.observe(3000,.1);
assert.equal(p.snapshot(7000).maxGapMs,0);p.setForeground(true,7000,true);
p.observe(7033,.2);p.setForeground(true,9000,true);
assert.equal(p.snapshot(9200).maxGapMs,2167); // commit cannot reset reveal anchor
p.retire(9300);assert.equal(p.snapshot(9500).maxGapMs,2267);
''')

    def test_pause_excludes_only_pause_and_preserves_prior_maximum(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);p.observe(0,0);
p.setRunning(false,500);assert.equal(p.snapshot(5000).maxGapMs,500);
p.setRunning(true,5000);p.observe(5033,.1);assert.equal(p.snapshot(5033).maxGapMs,533);
p.setRunning(false,7500);p.setRunning(true,10000);p.observe(10033,.2);
assert.equal(p.snapshot(10033).maxGapMs,2500);
''')

    def test_pause_preserves_active_gap_across_pause_and_paused_callbacks(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);p.observe(500,0);
p.setRunning(false,1400);p.setRunning(true,11400);p.observe(12500,.1);
assert.equal(p.snapshot(12500).maxGapMs,2000);
p.setRunning(false,13000);p.observe(14000,.2);p.setRunning(true,23000);p.observe(23033,.3);
assert.equal(p.snapshot(23033).currentGapMs,0);assert.equal(p.snapshot(23033).maxGapMs,2000);
const q=new FrameProgress(true);q.assign('blob:b',0);q.setForeground(true,1000,false);
q.observe(9000,0);q.setRunning(true,10000);q.observe(10033,.1);
assert.equal(q.snapshot(10033).maxGapMs,33);
''')

    def test_snapshot_seals_gap_and_source_epoch_rejects_earlier_callbacks(self):
        self.run_js('''
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);p.observe(0,0);
assert.equal(p.snapshot(2400).maxGapMs,2400);p.observe(2399,.1);
assert.equal(p.snapshot(2401).maxGapMs,2400);
p.retire(2500);p.assign('blob:b',3000);p.observe(2999,.2);
assert.equal(p.snapshot(3000).sourceChanges,0);
for(let i=0;i<200;i++)p.observe(3000+i,i);
const s=p.snapshot(3200,true);assert.equal(s.trace.length,128);
assert.equal(s.trace[0].wall,3072);assert.equal(s.trace.at(-1).wall,3199);
assert.equal(new FrameProgress(false).snapshot(0).supported,false);
''')

    def test_rest_does_not_reset_and_unload_archives_hold_before_native_error_clears(self):
        self.run_js('''
let wall=0;Object.defineProperty(globalThis,'performance',{value:{now:()=>wall}});
const p=new FrameProgress(true);p.assign('blob:a',0);p.setForeground(true,0,true);p.observe(0,0);
const media={dataset:{loopId:'one'},style:{},error:{code:3,message:'decode failure'},
  pause(){},removeAttribute(){},load(){this.error=null;},readyState:4,currentSrc:'blob:a',paused:false};
const deck={media,url:'blob:a',progress:p,proofDeck:0};
const node={id:'one',active:deck,decks:[deck],box:{style:{}}};
const session=Object.create(Session.prototype);Object.assign(session,{proof:true,proofRetired:[],
  proofRetiredCount:0,proofMaxGapMs:0,slots:new Map([['one',node]]),nodes:new Map([['one',node]]),
  events:[],clock:{simTime:0},updateNodeAudio(){}});
wall=1000;session.setResting('one',true);wall=2400;session.unload(deck);
let s=session.proofProgressSummary(3000,true);assert.equal(s.maxGapMs,2400);
assert.equal(s.retiredCount,1);assert.equal(s.retired[0].nativeError.code,3);
assert.equal(s.retired[0].url,'blob:a');assert.equal(s.retired[0].deck,0);
p.assign('blob:b',3000);assert.equal(session.proofProgressSummary(3000).maxGapMs,2400);
for(let i=0;i<20;i++){deck.url='blob:'+i;p.assign(deck.url,wall);session.unload(deck);}
s=session.proofProgressSummary(3000,true);assert.equal(s.retired.length,16);
assert.equal(s.retiredCount,21);assert.equal(s.maxGapMs,2400);
''')


class NativeFrameProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        from simvltanea.browser.test_browser_runtime import browser_executable
        from simvltanea.browser.test_browser_studio import prepare_fixtures
        cls.fixtures = prepare_fixtures()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=browser_executable(), headless=True,
                                           args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, proof=True):
        import base64
        context = self.browser.new_context()
        self.addCleanup(context.close)
        page = context.new_page()
        page.route('http://proof.test/**', lambda route: route.fulfill(
            content_type='text/html', body='<main id="stage" style="width:640px;height:360px"></main>'))
        page.goto('http://proof.test/' + ('?proof=1' if proof else ''))
        page.add_script_tag(path=str(LIVE))
        payload = [base64.b64encode(self.fixtures[f'loop-{i}.mp4'].read_bytes()).decode() for i in (1, 2)]
        page.evaluate('''payload=>{
          window.items=payload.map((x,i)=>({sha256:String(i),file:new Blob([
            Uint8Array.from(atob(x),c=>c.charCodeAt(0))],{type:'video/mp4'})}));
          const cells=[{loop:'one',rect:['0','0','1','1'],fit:'cover'}];
          window.plan={sources:[{id:'one'}],tracks:[{id:'one',spans:[{source:'one'}]}],
            layout_keyframes:[{layouts:{portrait:{cells},landscape:{cells}}}]};
          window.live=new SimvltaneaLive.Session(document.querySelector('#stage'),{crossfadeSec:.3});
          window.change=i=>live.reconcile({plan,items:[items[i]],playing:true});
        }''', payload)
        self.assertTrue(page.evaluate('change(0)'), page.evaluate('live.lastFailure'))
        return page

    def test_native_callback_progress_rest_pause_and_source_retirement(self):
        page = self.open()
        page.wait_for_function("live.nodes.get('one').active.progress.sourceChanges>3")
        page.evaluate("window.original=live.nodes.get('one').active;window.oldURL=original.url;live.setResting('one',true)")
        before = page.evaluate('original.progress.snapshot(performance.now())')
        page.wait_for_function('count=>original.progress.changes>count+3', arg=before['changes'])
        self.assertEqual(page.evaluate('original.progress.foregroundSince'), before['foregroundSince'])
        page.evaluate('live.pause()')
        paused = page.evaluate('original.progress.snapshot(performance.now())')
        page.wait_for_timeout(350)
        self.assertEqual(page.evaluate('original.progress.snapshot(performance.now()).maxGapMs'), paused['maxGapMs'])
        page.evaluate('live.start()')
        page.wait_for_function('count=>original.progress.changes>count', arg=before['changes'] + 4)
        page.evaluate('change(1)')
        summary = page.evaluate('live.proofProgressSummary(performance.now(),true)')
        self.assertTrue(summary['supported'])
        self.assertEqual(summary['suspensionCount'], 1)
        self.assertEqual(summary['retiredCount'], 1)
        self.assertEqual(summary['retired'][0]['url'], page.evaluate('oldURL'))
        self.assertGreater(len(summary['retired'][0]['trace']), 3)
        self.assertFalse(page.evaluate('original.progress.live'))
        self.assertTrue(page.evaluate("live.nodes.get('one').active.progress.foreground"))

    def test_revealed_incoming_stall_is_counted_before_identity_commits(self):
        page = self.open()
        page.evaluate('''()=>{live.crossfadeSec=1;window.pending=change(1);}''')
        page.wait_for_function('Boolean(live.fade)')
        self.assertTrue(page.evaluate('live.fade.incoming.progress.foreground && live.fade.outgoing.progress.foreground'))
        page.evaluate('''()=>{live.clock.pause();window.incoming=live.fade.incoming;
          window.outgoing=live.fade.outgoing;incoming.media.pause();}''')
        page.wait_for_timeout(2200)
        held = page.evaluate('incoming.progress.snapshot(performance.now())')
        self.assertGreater(held['maxGapMs'], 2000)
        self.assertEqual(page.evaluate("live.nodes.get('one').active===outgoing"), True)
        page.evaluate('incoming.media.play()')
        page.wait_for_function('count=>incoming.progress.changes>count', arg=held['changes'])
        page.evaluate('live.clock.start()')
        page.evaluate('pending')
        self.assertGreater(page.evaluate('live.proofProgressSummary(performance.now()).maxGapMs'), 2000)

    def test_ordinary_session_does_not_allocate_progress_trackers(self):
        page = self.open(proof=False)
        self.assertTrue(page.evaluate("[...live.slots.values()].every(n=>n.decks.every(d=>!d.progress))"))
        self.assertIsNone(page.evaluate('live.proofProgressSummary(performance.now(),true)'))
