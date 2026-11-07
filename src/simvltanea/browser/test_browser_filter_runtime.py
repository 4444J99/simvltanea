"""Regression coverage for adjustable per-deck effects on the persistent runtime."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

HERE = Path(__file__).parent

HOST = r"""
require(process.argv[1] + '/browser.presence.js');
const {Session} = require(process.argv[1] + '/browser.live.js');
const {Engine} = require(process.argv[1] + '/browser.ecosystem.js');
const supported = typeof Session.prototype.setEffectSettings === 'function';
if (!supported) {console.log(JSON.stringify({supported})); process.exit(0);}
const parameter = value => ({value, calls:[],
  setTargetAtTime(v,t,tau){this.value=v;this.calls.push({v,t,tau});},
  cancelScheduledValues(){}, setValueAtTime(v){this.value=v;}});
function deck(p, enteredAt=0, target=p) {
  return {media:{muted:false,style:{filter:'',opacity:'1'}},weight:1,presence:p,
    enteredAt,presenceTarget:target,binding:{target:0,cutoff:null,
      gain:{gain:parameter(0)},filter:{type:'lowpass',frequency:parameter(20000)}}};
}
function host() {
  const session=Object.create(Session.prototype), a=deck(.12), b=deck(.7);
  session.nodes=new Map([['one',{id:'one',decks:[a],active:a,targetGain:.8,resting:false}],
    ['two',{id:'two',decks:[b],active:b,targetGain:.2,resting:false}]]);
  Object.assign(session,{audio:{enabled:true,context:{state:'running',currentTime:7,sampleRate:48000}},
    sound:{enabled:true},running:true,options:{},fade:null,effectsEnabled:true,
    effectSettings:SimvltaneaPresence.DEFAULT_SETTINGS,proof:null,clock:{simTime:0}});
  return session;
}
"""


def execute(body):
    result = subprocess.run(['node', '-e', HOST + body, str(HERE)],
                            check=True, capture_output=True, text=True, timeout=20)
    return json.loads(result.stdout)


class FilterRuntimeModelTests(unittest.TestCase):
    def test_effects_can_be_adjusted_independently_on_existing_decks(self):
        result = execute(r"""
const s=host(), node=s.nodes.get('one'), active=node.active, binding=active.binding;
s.setPresence('one',.25);
const enabled={gain:binding.target,filter:active.media.style.filter,cutoff:binding.cutoff};
s.setEffectSettings({gainDepth:0,lowpassDepth:0,brightnessDepth:0,saturationDepth:0,blurPx:0});
console.log(JSON.stringify({supported,enabled,neutral:{gain:binding.target,filter:active.media.style.filter,
  type:binding.filter.type},same:node.active===active && active.binding===binding}));
""")
        self.assertTrue(result['supported'], 'adjustable runtime settings are missing')
        self.assertAlmostEqual(result['enabled']['gain'], .2)
        self.assertIn('blur(1.5px)', result['enabled']['filter'])
        self.assertEqual(result['neutral'], dict(gain=.8, filter='', type='allpass'))
        self.assertTrue(result['same'])

    def test_rising_successor_uses_same_settings_time_for_sound_and_image(self):
        result = execute(r"""
const s=host(), n=s.nodes.get('one'), sibling=s.nodes.get('two');
s.setEffectSettings({attackSeconds:4,curve:'smooth',gainDepth:.4});
const incoming=deck(0,10,null);incoming.weight=0;n.decks.push(incoming);
s.fade={node:n,incoming,outgoing:n.active,began:10,duration:4,finish(){}};
const oldSibling={p:sibling.active.presence,filter:sibling.active.media.style.filter,gain:sibling.active.binding.target};
s.tick(11);
console.log(JSON.stringify({supported,p:incoming.presence,weight:incoming.weight,
  gain:incoming.binding.target,filter:incoming.media.style.filter,cutoff:incoming.binding.cutoff,
  expected:SimvltaneaPresence.filterTargets(.15625,48000,s.effectSettings),
  oldSibling,sibling:{p:sibling.active.presence,filter:sibling.active.media.style.filter,gain:sibling.active.binding.target},
  oldAlpha:n.active.media.style.opacity,newAlpha:incoming.media.style.opacity}));
""")
        self.assertTrue(result['supported'], 'adjustable runtime settings are missing')
        self.assertAlmostEqual(result['p'], .15625)
        self.assertAlmostEqual(result['weight'], .25)
        self.assertAlmostEqual(result['gain'], .8 * .25 * result['expected']['gain'])
        self.assertAlmostEqual(result['cutoff'], result['expected']['cutoffHz'])
        self.assertIn('blur(1.688px)', result['filter'])
        self.assertEqual(result['sibling'], result['oldSibling'])
        self.assertEqual(result['oldAlpha'], '1')
        self.assertEqual(result['newAlpha'], '0.25')

    def test_scheduler_and_entrance_share_configurable_attack(self):
        result = execute(r"""
const e=new Engine({seed:1}), settings=SimvltaneaPresence.normalizeSettings({attackSeconds:4,curve:'smooth'});
const residents=[{id:'one',clipKey:'a',duration:2,age:0,hasAudio:true,energy:1}];
e.step(0,0,residents,{enabled:false,effectSettings:settings});
const out=e.step(1,.1,residents,{enabled:false,effectSettings:settings});
console.log(JSON.stringify({supported,p:out.presence[0],entrance:SimvltaneaPresence.entranceEnvelope(1,settings),gain:out.gains[0]}));
""")
        self.assertTrue(result['supported'], 'adjustable runtime settings are missing')
        self.assertAlmostEqual(result['p'], .15625)
        self.assertEqual(result['p'], result['entrance'])
        self.assertAlmostEqual(result['gain'], .85)

    def test_bypass_does_not_overwrite_external_spectral_filter_each_frame(self):
        result = execute(r"""
const s=host(), d=s.nodes.get('one').active;
s.setEffects(false);d.presenceTarget=null;d.enteredAt=0;
d.binding.filter.type='lowpass';d.binding.filter.frequency.value=30;
s.tick(.5);s.tick(.6);
console.log(JSON.stringify({supported,type:d.binding.filter.type,frequency:d.binding.filter.frequency.value}));
""")
        self.assertTrue(result['supported'], 'adjustable runtime settings are missing')
        self.assertEqual(result['type'], 'lowpass')
        self.assertEqual(result['frequency'], 30)



class FilterRuntimeBrowserTests(unittest.TestCase):
    """Native decode and audio evidence, using the existing synthetic fixtures."""

    @classmethod
    def setUpClass(cls):
        from simvltanea.browser import test_browser_live as live_tests
        live_tests.PersistentSessionTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from simvltanea.browser import test_browser_live as live_tests
        live_tests.PersistentSessionTests.tearDownClass.__func__(cls)

    def open(self):
        from simvltanea.browser import test_browser_live as live_tests
        return live_tests.PersistentSessionTests.open(self, has_touch=True, effects=True)

    def unlock(self, page):
        page.evaluate("document.addEventListener('click',()=>{window.unlocked=live.unlock();live.setSound({enabled:true,volume:.5})},{once:true})")
        page.mouse.click(10, 10)
        page.evaluate('unlocked')

    def test_adjusting_one_effect_preserves_native_media_and_audio_graph(self):
        page = self.open()
        self.unlock(page)
        result = page.evaluate(r"""() => {
          const node=live.nodes.get('loop-1'),media=node.media,binding=node.audio,context=live.audio.context;
          live.clock.pause();live.setPresence('loop-1',.25);live.setTargetGain('loop-1',.8);
          const before=node.active.media.style.filter;
          live.setEffectSettings({gainDepth:0,lowpassDepth:0,brightnessDepth:0,blurPx:1});
          return {before,after:node.media.style.filter,type:node.audio.filter.type,gain:node.audio.target,
            same:node.media===media && node.audio===binding && live.audio.context===context,
            p:node.active.presence,paused:media.paused,budget:live.snapshot().maxConcurrentStandbys};
        }""")
        self.assertIn('brightness(', result['before'])
        self.assertNotIn('brightness(', result['after'])
        self.assertIn('saturate(0.475)', result['after'])
        self.assertIn('blur(0.75px)', result['after'])
        self.assertEqual(result['type'], 'allpass')
        self.assertAlmostEqual(result['gain'], .8)
        self.assertTrue(result['same'])
        self.assertFalse(result['paused'])
        self.assertEqual(result['p'], .25)
        self.assertEqual(result['budget'], 1)

    def test_simultaneous_envelopes_and_queued_handoffs_keep_siblings_playing(self):
        page = self.open()
        self.unlock(page)
        page.evaluate(r"""() => {
          live.setPresence('loop-1',.2);live.setPresence('loop-2',.8);
          live.crossfadeSec=.8;window.sibling=live.nodes.get('loop-2');window.siblingMedia=sibling.media;
          window.siblingAudio=sibling.audio;window.siblingCalls=[];
          for(const name of ['play','pause','load']) {const native=siblingMedia[name].bind(siblingMedia);
            siblingMedia[name]=(...args)=>{siblingCalls.push(name);return native(...args)};}
          window.change=setClips([2,3]);
        }""")
        page.wait_for_function('Boolean(live.fade)')
        state = page.evaluate(r"""() => {
          const fade=live.fade;live.clock.pause();live.tick(fade.began+.4);
          live.setPresence('loop-2',.6);
          return {incoming:fade.incoming.presence,outgoing:fade.outgoing.presence,sibling:sibling.active.presence,
            same:sibling.media===siblingMedia && sibling.audio===siblingAudio,calls:siblingCalls,
            siblingFrames:sibling.callbacks,permit:live.snapshot().activeStandbys,
            populated:[...document.querySelectorAll('video')].filter(v=>v.getAttribute('src')).length};
        }""")
        self.assertAlmostEqual(state['incoming'], 1 / 3)
        self.assertEqual(state['outgoing'], .2)
        self.assertEqual(state['sibling'], .6)
        self.assertTrue(state['same'])
        self.assertEqual(state['calls'], [])
        self.assertEqual(state['permit'], 1)
        self.assertEqual(state['populated'], 3)
        page.evaluate('live.clock.start()')
        page.evaluate('change')
        self.assertEqual(page.evaluate('[...live.nodes.values()].map(n=>n.item.name)'), ['clip-2', 'clip-3'])
        self.assertEqual(page.evaluate('live.snapshot().activeStandbys'), 0)
        self.assertEqual(page.evaluate('live.snapshot().maxConcurrentStandbys'), 1)

    def test_frozen_successor_restores_outgoing_envelope_and_releases_permit(self):
        page = self.open()
        self.unlock(page)
        page.evaluate(r"""() => {
          const node=live.nodes.get('loop-1');live.setPresence(node.id,.12);
          window.old={media:node.media,item:node.item,born:node.birthTime,entered:node.active.enteredAt,
            binding:node.audio,filter:node.media.style.filter};
          const next=node.decks.find(d=>d!==node.active).media,play=next.play.bind(next);
          next.play=()=>{if(next.dataset.deck!=='active')return play();next.pause();return Promise.resolve()};
        }""")
        self.assertFalse(page.evaluate('setClips([2,1])'))
        state = page.evaluate(r"""() => {const n=live.nodes.get('loop-1');return {
          same:n.media===old.media && n.item===old.item && n.birthTime===old.born &&
            n.active.enteredAt===old.entered && n.audio===old.binding,
          presence:n.active.presence,filter:n.media.style.filter,previousFilter:old.filter,
          moving:!n.media.paused,muted:n.media.muted,permit:live.snapshot().activeStandbys,
          gain:n.audio.target,standbyEmpty:n.decks.filter(d=>d!==n.active).every(d=>!d.url && !d.media.style.filter)};}""")
        self.assertTrue(state['same'])
        self.assertEqual(state['presence'], .12)
        self.assertEqual(state['filter'], state['previousFilter'])
        self.assertTrue(state['moving'])
        self.assertFalse(state['muted'])
        self.assertGreater(state['gain'], 0)
        self.assertEqual(state['permit'], 0)
        self.assertTrue(state['standbyEmpty'])

    def test_audio_and_visual_targets_share_presence_and_settle_together(self):
        page = self.open()
        self.unlock(page)
        page.evaluate(r"""() => {
          live.clock.pause();live.setEffectSettings({gainDepth:.5,lowpassDepth:.75,blurPx:1});
          live.setTargetGain('loop-1',.8);live.setPresence('loop-1',1);
        }""")
        page.wait_for_timeout(120)
        state = page.evaluate(r"""() => {live.setPresence('loop-1',.25);const n=live.nodes.get('loop-1');
          return {p:n.active.presence,expected:SimvltaneaPresence.filterTargets(.25,live.audio.context.sampleRate,live.effectSettings),
            gain:n.audio.target,cutoff:n.audio.cutoff,style:n.media.style.filter};}""")
        self.assertEqual(state['p'], .25)
        self.assertAlmostEqual(state['gain'], .8 * state['expected']['gain'])
        self.assertAlmostEqual(state['cutoff'], state['expected']['cutoffHz'])
        self.assertIn('blur(0.75px)', state['style'])
        page.wait_for_timeout(100)
        actual = page.evaluate("({gain:live.nodes.get('loop-1').audio.gain.gain.value,cutoff:live.nodes.get('loop-1').audio.filter.frequency.value})")
        self.assertAlmostEqual(actual['gain'], state['gain'], delta=.003)
        self.assertAlmostEqual(actual['cutoff'], state['cutoff'], delta=30)


if __name__ == '__main__':
    unittest.main()
