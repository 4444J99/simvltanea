import math

import pytest

from simvltanea.lab.tests.e2e.helpers import GEOMETRY_JS


# The speech policy defaults to mute (and unscreened clips are muted too); these tests exercise the audio graph itself.
PLAY = {"audio.speech_policy": "play", "audio.mute_unscreened": False}


def start(lab):
    lab.page.click("#start-btn")
    lab.page.wait_for_function("__lab.audioStarted() === true")
    lab.page.wait_for_function("__lab.audio().every(a => a.ctxState === 'running')", timeout=5000)
    lab.page.wait_for_function("__lab.player.audio.ctx.currentTime > 0.8", timeout=8000)
    lab.page.wait_for_timeout(300)


def freeze(lab):
    """Long holds, then re-pick once, so no clip change (and fade) happens while a test measures gains."""
    lab.set("timing.hold_min", 60)
    lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.settle(1200)


def expected_norm(clip, target=-30):
    if not clip.get("has_audio", True):
        return 0
    if clip.get("loudness_db") is None:
        return 1
    return 10 ** (max(-40, min(20, target - clip["loudness_db"])) / 20)


def test_audio_is_off_until_start_and_videos_play_muted_first(lab):
    assert lab.js("__lab.audioStarted()") is False
    assert lab.js("[...document.querySelectorAll('video.on')].every(v => v.muted)")
    assert lab.page.locator("#start-btn").is_visible()
    assert lab.page.locator("#btn-sound").text_content() == "Sound: off"


def test_after_start_every_panel_is_unmuted_routed_and_panned_distinctly(make_lab):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set_panels(5)
    start(lab)
    assert not lab.page.locator("#start-btn").is_visible()
    audio = lab.js("__lab.audio()")
    assert len(audio) == 5
    for a in audio:
        assert a["elementMuted"] is False and a["routed"] is True
        assert a["ctxState"] == "running"
    pans = [a["pan"] for a in audio]
    assert len(set(pans)) == 5 and pans == sorted(pans)
    assert pans[0] == pytest.approx(-0.8 * 0.8, abs=0.2) or pans[0] < -0.4
    assert abs(pans[0] + pans[-1]) < 0.01 and abs(pans[2]) < 0.01
    # actual Web Audio StereoPanner values follow
    assert [round(a["panValue"], 3) for a in lab.js("__lab.audio()")] == [round(p, 3) for p in pans]
    # videos are really playing through the graph (currentTime advancing, not paused)
    assert lab.js("[...document.querySelectorAll('video.on')].every(v => !v.paused && !v.muted)")
    # VU: signal really reaches the analysers (meters move) for panels that have audio
    lab.page.wait_for_function("__lab.audio().some(a => a.level > 0.001)", timeout=5000)
    assert lab.js("__lab.player.levels.some(v => v > 0.05)")
    lab.set("audio.pan", False)
    lab.settle(400)
    assert all(a["panValue"] == 0 for a in lab.js("__lab.audio()"))
    lab.set("audio.pan", True)
    lab.set("audio.pan_width", 0.2)
    lab.settle(400)
    assert max(abs(a["panValue"]) for a in lab.js("__lab.audio()")) <= 0.2 + 1e-6
    assert lab.errors == []


def test_pan_in_a_tall_viewport_uses_the_strip_axis(make_lab):
    lab = make_lab((375, 812))
    lab.open(values=PLAY)
    lab.set_panels(4)
    start(lab)
    pans = [a["pan"] for a in lab.js("__lab.audio()")]
    assert len(set(pans)) == 4 and pans == sorted(pans)


def test_gain_follows_loudness_normalisation(make_lab, clips):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set_panels(8)
    freeze(lab)
    start(lab)
    audio = lab.js("__lab.audio()")
    rows = []
    for a in audio:
        c = clips[a["clip"]]
        assert a["norm"] == pytest.approx(expected_norm(c), rel=1e-3), (c["id"], c.get("loudness_db"))
        assert a["slotGain"] == pytest.approx(a["norm"], rel=0.02, abs=1e-3), "the Web Audio gain node holds the normalised value"
        rows.append((c.get("loudness_db"), a["norm"]))
    known = sorted((l, n) for l, n in rows if l is not None and n > 0)
    assert len(known) >= 4
    assert len({round(l) for l, _ in known}) >= 2, "fixtures have different levels on screen"
    norms = [n for _, n in known]
    assert norms == sorted(norms, reverse=True), "louder clip -> lower gain: %s" % known
    # target knob moves every gain by the same number of dB
    lab.set("audio.norm_target_db", -20)
    lab.settle(600)
    for a in lab.js("__lab.audio()"):
        c = clips[a["clip"]]
        assert a["norm"] == pytest.approx(expected_norm(c, -20), rel=1e-3)
        assert a["slotGain"] == pytest.approx(a["norm"], rel=0.03, abs=1e-3)
    lab.set("audio.normalize", False)
    lab.settle(600)
    for a in lab.js("__lab.audio()"):
        assert a["norm"] == (1 if clips[a["clip"]].get("has_audio", True) else 0)
        assert a["slotGain"] == pytest.approx(a["norm"], abs=0.02)


def test_size_weighted_gain_and_auto_trim(make_lab):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set("layout.split", "golden")
    lab.set("audio.size_gain", 1)
    lab.set_panels(4)
    freeze(lab)
    start(lab)
    sizes = [a["size"] for a in lab.js("__lab.audio()")]
    assert sizes[0] > sizes[1] > sizes[2] > sizes[3]
    busses = [a["busGain"] for a in lab.js("__lab.audio()")]
    assert busses == pytest.approx(sizes, rel=0.02)
    lab.set("audio.size_gain", 0)
    lab.settle(500)
    assert all(a["busGain"] == pytest.approx(1, abs=0.02) for a in lab.js("__lab.audio()"))


def test_mute_and_solo(make_lab):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set_panels(4)
    freeze(lab)
    start(lab)
    lab.page.locator('[data-param="audio.muted_panels"] [data-option="2"]').click()
    lab.settle(500)
    a = lab.js("__lab.audio()")
    assert a[1]["muted"] and a[1]["mute"] and a[1]["gain"] == 0 and a[1]["busGain"] == pytest.approx(0, abs=0.01)
    assert not a[0]["muted"] and a[0]["busGain"] > 0.5
    assert lab.page.locator('.panel[data-panel="1"] .pmute').get_attribute("aria-pressed") == "true"
    # solo
    lab.page.locator('[data-param="audio.solo_panels"] [data-option="3"]').click()
    lab.settle(500)
    a = lab.js("__lab.audio()")
    assert [x["muted"] for x in a] == [True, True, False, True]
    assert a[2]["busGain"] > 0.5 and all(a[i]["busGain"] == pytest.approx(0, abs=0.01) for i in (0, 1, 3))
    # a soloed panel that is also muted stays silent; clearing restores
    lab.page.locator('[data-param="audio.muted_panels"] [data-option="3"]').click()
    lab.settle(300)
    assert [x["muted"] for x in lab.js("__lab.audio()")] == [True, True, True, True]
    lab.page.locator('[data-param="audio.muted_panels"] [data-option="3"]').click()
    lab.page.locator('[data-param="audio.solo_panels"] [data-option="3"]').click()
    lab.page.locator('[data-param="audio.muted_panels"] [data-option="2"]').click()
    lab.settle(500)
    assert [x["muted"] for x in lab.js("__lab.audio()")] == [False] * 4
    # the buttons on the panels do the same (they appear on hover, not for tiny strips)
    lab.page.locator('.panel[data-panel="0"]').hover(position={"x": 40, "y": 600})
    lab.page.locator('.panel[data-panel="0"] .psolo').click(force=True)
    lab.settle(400)
    assert lab.js("__lab.params()['audio.solo_panels']") == [1]
    assert lab.js("__lab.reveal().open") is False, "tool buttons do not open the reveal"
    lab.page.locator('.panel[data-panel="0"] .psolo').click(force=True)
    assert lab.js("__lab.params()['audio.solo_panels']") == []


def test_clips_without_audio_are_silent_and_respected(make_lab, clips):
    silent = next(c for c in clips.values() if c.get("has_audio") is False)
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set("source.tags_include", [silent["tags"]["environment"]])
    lab.set("source.untagged", "include")
    lab.set_panels(4)  # exactly the 4 matching clips are on screen
    freeze(lab)
    start(lab)
    audio = lab.js("__lab.audio()")
    sil = [a for a in audio if a["clip"] == silent["id"]]
    assert sil, "the clip without an audio track is on screen: %s" % [a["clip"] for a in audio]
    assert sil[0]["hasAudio"] is False and sil[0]["gain"] == 0 and sil[0]["slotGain"] == pytest.approx(0, abs=1e-3)
    others = [a for a in audio if a["clip"] != silent["id"]]
    assert all(a["gain"] > 0 for a in others)


def test_limiter_and_master(make_lab):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    start(lab)
    lab.set("audio.master", 1.5)
    lab.set("audio.limiter", False)
    lab.settle(300)
    assert lab.js("__lab.player.audio.comp.ratio.value") == 1
    lab.set("audio.limiter", True)
    lab.set("audio.limiter_ceiling", -12)
    lab.settle(300)
    assert lab.js("__lab.player.audio.comp.threshold.value") == pytest.approx(-12)
    assert lab.js("__lab.player.audio.comp.ratio.value") >= 12
    # master x 1/sqrt(N) auto trim
    g = lab.js("__lab.player.audio.master.gain.value")
    assert g == pytest.approx(1.5 / math.sqrt(4), rel=0.02)
    lab.set("audio.auto_trim", False)
    lab.settle(300)
    assert lab.js("__lab.player.audio.master.gain.value") == pytest.approx(1.5, rel=0.02)


def test_clip_change_fades_instead_of_clicking(make_lab):
    lab = make_lab((1280, 720))
    lab.open(values=PLAY)
    lab.set("timing.hold_min", 2)
    lab.set("timing.hold_max", 2)
    lab.set("audio.fade", 0.8)
    lab.set_panels(2)
    lab.js("__lab.player.sched.reset(__lab.player.t)")   # the first hold was drawn from the default 4-10 s: redraw it from 2 s
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    start(lab)
    # sample the slot gains of panel 0 while its clip changes: never a jump from 0 to >0.5 within 50ms
    samples = lab.js("""async () => {
      const out = []; const p = __lab.player.panels[0];
      const t0 = performance.now();
      while (performance.now() - t0 < 6500) {
        out.push(p.slots.map(s => (s.gain ? s.gain.gain.value : 0)));
        await new Promise(r => setTimeout(r, 25));
      }
      return out; }""")
    assert len(samples) > 50
    biggest = 0
    for a, b in zip(samples, samples[1:]):
        for i in (0, 1):
            biggest = max(biggest, abs(b[i] - a[i]))
    peak = max(max(s) for s in samples)
    assert peak > 0
    assert biggest < 0.5 * peak, "gain steps (%.3f of peak %.3f) would click" % (biggest, peak)
    # both slots were audible simultaneously at some point = cross-fade
    assert any(s[0] > 0.05 * peak and s[1] > 0.05 * peak for s in samples)
