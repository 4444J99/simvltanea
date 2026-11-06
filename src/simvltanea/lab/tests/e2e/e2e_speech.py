import pytest

from simvltanea.lab.tests.e2e.e2e_audio import freeze, start

SPEECH_FLAGS = {"number_sequence", "email_like", "introduces_self", "possible_name", "long_speech"}


def has_speech(c):
    a = c.get("audio") or {}
    return a.get("speech") is True or bool(SPEECH_FLAGS & set(a.get("flags") or []))


def unscreened(c):
    return (c.get("audio") or {}).get("screened") is not True


def test_the_fixture_dataset_has_roughly_a_third_speech_clips(clips):
    n = sum(1 for c in clips.values() if has_speech(c))
    assert 5 <= n <= 11 and any(unscreened(c) for c in clips.values())
    flags = {f for c in clips.values() for f in (c.get("audio") or {}).get("flags", [])}
    assert {"introduces_self", "possible_name", "number_sequence", "long_speech"} <= flags


def test_defaults_are_mute_and_mute_unscreened(lab):
    p = lab.js("__lab.params()")
    assert p["audio.speech_policy"] == "mute" and p["audio.mute_unscreened"] is True
    assert lab.page.locator("#in-audio-speech_policy").input_value() == "mute"
    assert lab.page.locator('[data-param="audio.mute_unscreened"] [role=switch]').get_attribute("aria-checked") == "true"
    assert lab.page.locator('.module[data-module="audio"] [data-param="audio.speech_policy"]').count() == 1


def test_mute_picture_plays_sound_does_not_and_play_restores_it_through_the_real_control(make_lab, clips):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set_panels(12)
    freeze(lab)
    start(lab)
    lab.page.select_option("#in-audio-speech_policy", "mute")
    lab.page.locator('[data-param="audio.mute_unscreened"] [role=switch]').click()    # off: only the speech rule remains
    lab.settle(400)
    audio = lab.js("__lab.audio()")
    speechy = [a for a in audio if has_speech(clips[a["clip"]])]
    clean = [a for a in audio if not has_speech(clips[a["clip"]]) and clips[a["clip"]].get("has_audio", True)]
    assert len(speechy) >= 2 and len(clean) >= 2, (len(speechy), len(clean))
    for a in speechy:
        assert a["gain"] == 0 and a["speechMuted"] is True and a["elementMuted"] is True, a
        assert a["slotGain"] == pytest.approx(0, abs=1e-3)
    for a in clean:
        assert a["gain"] > 0 and a["speechMuted"] is False and a["elementMuted"] is False and a["slotGain"] > 0, a
    # the picture keeps playing under mute
    assert lab.js("[...document.querySelectorAll('video.on')].filter((v) => v.getAttribute('src')).every((v) => !v.paused || v.readyState < 2)")
    assert lab.js("__lab.audio().every((a) => a.clip)")
    # play: speech clips sound again
    lab.page.select_option("#in-audio-speech_policy", "play")
    lab.settle(900)
    for a in lab.js("__lab.audio()"):
        if has_speech(clips[a["clip"]]) and clips[a["clip"]].get("has_audio", True):
            assert a["gain"] > 0 and a["speechMuted"] is False and a["slotGain"] > 0, a
    assert lab.errors == []


def test_unscreened_clips_are_silent_until_the_switch_is_turned_off(make_lab, clips):
    lab = make_lab((1280, 720))
    lab.open(values={"audio.speech_policy": "play"})
    lab.set("source.tags_include", ["urban"])        # a small pool that contains the unscreened fixture clip (and untagged ones)
    lab.set_panels(8)
    freeze(lab)
    start(lab)
    audio = lab.js("__lab.audio()")
    un = [a for a in audio if unscreened(clips[a["clip"]])]
    assert un, "an unscreened clip is on screen: %s" % [a["clip"] for a in audio]
    for a in un:
        assert a["gain"] == 0 and a["speechReason"] == "unscreened" and a["elementMuted"] is True and a["slotGain"] == pytest.approx(0, abs=1e-3)
    lab.page.locator('[data-param="audio.mute_unscreened"] [role=switch]').click()
    lab.settle(700)
    for a in lab.js("__lab.audio()"):
        if unscreened(clips[a["clip"]]) and clips[a["clip"]].get("has_audio", True):
            assert a["gain"] > 0 and a["elementMuted"] is False, a


def test_exclude_never_shows_a_speech_clip_even_one_that_is_already_on_screen(make_lab, clips):
    lab = make_lab((1280, 720))
    lab.open(values={"audio.speech_policy": "play"})
    lab.set_panels(10)
    lab.settle(600)
    before = lab.js("__lab.engine()")
    assert any(has_speech(clips[c]) for c in before), "precondition: speech on screen"
    pool_before = lab.js("__lab.pool()")
    lab.page.select_option("#in-audio-speech_policy", "exclude")
    lab.page.wait_for_function("(n) => __lab.pool() < n", arg=pool_before)
    assert lab.js("__lab.pool()") <= sum(1 for c in clips.values() if not has_speech(c))
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.settle(1800)
    for _ in range(12):
        shown = lab.js("__lab.engine()")
        assert not any(has_speech(clips[c]) for c in shown), [c for c in shown if has_speech(clips[c])]
        lab.page.wait_for_timeout(500)
    lab.set("timing.hold_min", 0.5); lab.set("timing.hold_max", 0.8); lab.set("timing.cooldown", 0)
    for _ in range(25):
        assert not any(has_speech(clips[c]) for c in lab.js("__lab.engine()"))
        lab.page.wait_for_timeout(300)
    assert lab.errors == []


def test_the_reveal_of_a_muted_clip_stays_muted(make_lab, clips):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set_panels(12)
    freeze(lab)
    start(lab)
    lab.set("reveal.action", "both")
    lab.set("reveal.animation", "none")
    k = next(a["panel"] for a in lab.js("__lab.audio()") if has_speech(clips[a["clip"]]))
    lab.page.locator('.panel[data-panel="%d"]' % k).click(position={"x": 10, "y": 10})
    lab.page.wait_for_selector(".reveal video.reveal-video")
    assert lab.js("document.querySelector('.reveal video').muted") is True
    assert lab.page.locator(".reveal img.reveal-still").count() == 1, "the old photo still shows"
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    # a clean, screened clip's reveal is audible (muted only before Start)
    j = next(a["panel"] for a in lab.js("__lab.audio()") if not has_speech(clips[a["clip"]]) and not unscreened(clips[a["clip"]]))
    lab.page.locator('.panel[data-panel="%d"]' % j).click(position={"x": 10, "y": 10})
    lab.page.wait_for_selector(".reveal video.reveal-video")
    assert lab.js("document.querySelector('.reveal video').muted") is False, "policy-clean clips keep their sound in the reveal"
    lab.page.keyboard.press("Escape")


def test_randomize_and_presets_never_change_the_speech_policy(make_lab):
    lab = make_lab()
    lab.open(values={"audio.speech_policy": "exclude"})
    for _ in range(6):
        lab.page.click("#btn-randomize")
        p = lab.js("__lab.params()")
        assert p["audio.speech_policy"] == "exclude" and p["audio.mute_unscreened"] is True
    for pid in lab.js("[...document.querySelectorAll('#preset-select option')].map((o) => o.value).filter(Boolean)"):
        lab.page.locator("#preset-select").select_option(pid)
        assert lab.js("__lab.params()['audio.speech_policy']") == "exclude", pid
    lab.page.click("#btn-reset-all")
    assert lab.js("__lab.params()['audio.speech_policy']") == "mute"
