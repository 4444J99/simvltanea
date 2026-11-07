import json

import pytest

from simvltanea.lab.tests.e2e.helpers import APP, DATA, FIXTURES, GEOMETRY_JS, check_tiling


def video_transforms(lab):
    return lab.js("[...document.querySelectorAll('.panel video.on')].map(v => v.style.transform)")


def test_reduced_motion_disables_jitter_drift_and_animation(make_lab):
    lab = make_lab((1280, 720), reduced_motion="reduce")
    lab.open()
    assert lab.js("__lab.reduced()") is True
    assert lab.js("document.documentElement.classList.contains('reduced-motion')")
    lab.set("layout.jitter", 60)
    lab.set("layout.jitter_rate", 2)
    lab.set("zoom.focal_mode", "drift")
    lab.set("zoom.drift_speed", 30)
    lab.set("timing.hold_min", 60)
    lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.settle(1500)
    a = video_transforms(lab)
    lab.page.wait_for_timeout(900)
    assert video_transforms(lab) == a, "nothing moves under prefers-reduced-motion"
    # reveal opens instantly, with no transition
    lab.set("reveal.anim_ms", 1000)
    lab.page.keyboard.press("h")
    lab.page.locator('.panel[data-panel="1"]').click(position={"x": 8, "y": 8})
    lab.page.wait_for_selector(".reveal")
    assert lab.page.locator(".reveal").evaluate("e => e.style.transition") == ""
    assert lab.page.locator(".reveal").evaluate("e => getComputedStyle(e).clipPath") in ("none", "inset(0px)", "inset(0px 0px 0px 0px)")
    # crossfade between clips is instant
    assert lab.js("getComputedStyle(document.querySelector('.panel video.on')).transitionDuration") in ("0s", "0.0s")
    check_tiling(lab.js(GEOMETRY_JS))


def test_motion_is_on_without_the_preference(make_lab):
    lab = make_lab((1280, 720), reduced_motion="no-preference")
    lab.open()
    assert lab.js("__lab.reduced()") is False
    lab.set("layout.jitter", 60)
    lab.set("layout.jitter_rate", 2)
    lab.set("zoom.focal_mode", "drift")
    lab.set("zoom.drift_speed", 30)
    lab.set("timing.hold_min", 60)
    lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.settle(1500)
    seen = set()
    for _ in range(8):
        seen.add(tuple(video_transforms(lab)))
        lab.page.wait_for_timeout(120)
    assert len(seen) >= 4, "jitter and drift move the videos"
    for _ in range(6):
        check_tiling(lab.js(GEOMETRY_JS))
        lab.page.wait_for_timeout(100)


def test_reduced_motion_can_toggle_live(make_lab):
    lab = make_lab((1280, 720), reduced_motion="no-preference")
    lab.open()
    lab.set("layout.jitter", 40)
    lab.set("zoom.focal_mode", "drift")
    lab.set("timing.hold_min", 60)
    lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.settle(1500)
    lab.page.emulate_media(reduced_motion="reduce")
    lab.settle(600)
    assert lab.js("__lab.reduced()") is True
    a = video_transforms(lab)
    lab.page.wait_for_timeout(700)
    assert video_transforms(lab) == a


def test_h_hides_everything_and_docking(lab):
    assert lab.page.locator("#rack").is_visible()
    lab.page.keyboard.press("h")
    assert not lab.page.locator("#rack").is_visible()
    assert not lab.page.locator("#start-btn").is_visible()
    assert lab.js("getComputedStyle(document.querySelector('.panel .vu')).display") == "none"
    lab.page.keyboard.press("H")
    assert lab.page.locator("#rack").is_visible()
    for dock in ("left", "bottom", "right"):
        lab.page.click('[data-dock-set="%s"]' % dock)
        assert lab.page.locator("#rack").get_attribute("data-dock") == dock
        box = lab.page.locator("#rack").bounding_box()
        if dock == "left":
            assert box["x"] == 0 and box["height"] == 720
        elif dock == "right":
            assert box["x"] + box["width"] == 1280 and box["height"] == 720
        else:
            assert box["y"] + box["height"] == 720 and box["width"] == 1280
        check_tiling(lab.js(GEOMETRY_JS))  # the panel never changes the full-bleed layout
    lab.page.click("#rack-hide")
    assert not lab.page.locator("#rack").is_visible()
    # typing in a field does not trigger the hotkeys
    lab.page.keyboard.press("h")
    lab.page.fill("#patch-name", "")
    lab.page.focus("#patch-name")
    lab.page.keyboard.type("hh ")
    assert lab.page.locator("#rack").is_visible()
    assert lab.page.input_value("#patch-name") == "hh "
    assert lab.js("__lab.paused()") is False


def test_collapse_all_and_modules_present(lab):
    mods = lab.js("[...document.querySelectorAll('.module')].map(m => m.dataset.module)")
    assert mods == ["patch", "source", "order", "path", "relation", "timing", "layout", "zoom", "framing", "audio", "reveal"]
    lab.page.click("#rack-collapse")
    assert lab.page.locator(".module.collapsed").count() == 11
    lab.page.click("#rack-collapse")
    assert lab.page.locator(".module.collapsed").count() == 0
    for m in mods[1:]:
        assert lab.page.locator('[data-module="%s"] .byp' % m).count() == 1
        assert lab.page.locator('[data-module="%s"] .rst' % m).count() == 1


def test_phone_bottom_sheet(make_lab):
    lab = make_lab((375, 812), has_touch=True, is_mobile=True)
    lab.open()
    rack = lab.page.locator("#rack")
    assert lab.page.locator("#ui-fab").is_visible()
    box = rack.bounding_box()
    assert box is None or box["y"] >= 812 - 1 or not rack.is_visible() or box["y"] >= 700, "sheet starts closed"
    lab.page.tap("#ui-fab")
    lab.page.wait_for_timeout(500)
    box = rack.bounding_box()
    assert box["x"] == 0 and box["width"] == 375 and box["y"] + box["height"] == pytest.approx(812, abs=1)
    assert box["height"] < 812 * 0.7, "bottom sheet, not full screen"
    assert lab.page.locator('[data-param="layout.panels"] [role=slider]').is_visible()
    lab.page.tap("#ui-fab")
    lab.page.wait_for_timeout(500)
    assert rack.bounding_box()["y"] >= 790
    check_tiling(lab.js(GEOMETRY_JS))
    assert lab.js("__lab.axis()") == "rows"
    # panels are tappable on touch
    lab.page.locator('.panel[data-panel="1"]').tap(position={"x": 20, "y": 10})
    lab.page.wait_for_selector(".reveal")
    lab.page.tap(".reveal-close")
    lab.page.wait_for_selector(".reveal", state="detached")


def test_missing_data_shows_a_message_not_a_crash(make_lab):
    lab = make_lab()
    lab.open(data="/does-not-exist/", wait=False)
    lab.page.wait_for_selector("#message:not([hidden])")
    assert "could not load" in lab.page.locator("#message").text_content().lower()
    assert lab.page.locator("#rack").is_visible()
    assert not [e for e in lab.errors if e.startswith("pageerror")]


def test_cross_origin_data_base_is_refused_without_a_request(make_lab):
    lab = make_lab()
    lab.open(data="http://example.invalid/lab/", wait=False)
    lab.page.wait_for_selector("#message:not([hidden])")
    assert "same-origin" in lab.page.locator("#message").text_content()
    assert not [u for u in lab.requests if __import__("urllib.parse").parse.urlparse(u).hostname == "example.invalid"]


def test_default_data_base_is_relative(make_lab, server):
    lab = make_lab()
    lab.page.goto(server + APP)
    lab.page.wait_for_selector("#message:not([hidden])")
    assert any(u.endswith("/app/data/clips.json") for u in lab.requests)


def test_large_dataset_in_the_browser(make_lab):
    big = open(FIXTURES + "/data/clips-large.json", encoding="utf-8").read()
    lab = make_lab((1280, 720))
    lab.page.route("**/data/clips.json", lambda r: r.fulfill(status=200, content_type="application/json", body=big))
    lab.page.route(lambda u: "/media/" in u or "/still/" in u, lambda r: r.abort())
    lab.page.goto(lab.server + APP + "?data=" + DATA)
    lab.page.wait_for_function("window.__labReady === true", timeout=20000)
    assert lab.js("__lab.records()") >= 6400
    assert lab.js("__lab.pool()") >= 5000
    lab.set("layout.panels", 16)
    lab.set("order.axis", "captured_at")
    lab.set("path.shape", "converge")
    lab.set("relation.strength", 2)
    lab.page.wait_for_timeout(2500)
    # frame time while 16 panels schedule on 6,500 clips (media blocked, so this measures the engine + layout loop)
    ft = lab.js("""async () => { const t = []; let last = performance.now();
      await new Promise((res) => { const f = (n) => { t.push(n - last); last = n; t.length < 120 ? requestAnimationFrame(f) : res(); }; requestAnimationFrame(f); });
      t.sort((a, b) => a - b); return {median: t[60], p95: t[Math.floor(t.length * 0.95)]}; }""")
    print("frame ms with 6500 clips / 16 panels:", ft)
    assert ft["median"] < 40
    assert not [e for e in lab.errors if e.startswith("pageerror")]
