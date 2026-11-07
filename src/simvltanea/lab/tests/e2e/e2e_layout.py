import math

import pytest

from simvltanea.lab.tests.e2e.helpers import GEOMETRY_JS, check_tiling

VIEWPORTS = [(375, 812), (812, 375), (1280, 720), (1024, 1024), (320, 320), (2400, 600)]
COUNTS = [1, 2, 3, 5, 8, 12, 16]


def test_loads_without_console_errors_and_plays(make_lab):
    lab = make_lab()
    lab.open()
    lab.page.wait_for_timeout(2500)
    assert lab.errors == []
    ids = lab.js("__lab.engine()")
    assert len(ids) == 4 and all(ids) and len(set(ids)) == len(ids)
    states = lab.js("[...document.querySelectorAll('video.on')].map(v => ({rs: v.readyState, paused: v.paused, t: v.currentTime}))")
    assert len(states) >= 4 and all(s["rs"] >= 2 and not s["paused"] and s["t"] > 0 for s in states), states
    lab.page.wait_for_timeout(600)
    t2 = lab.js("[...document.querySelectorAll('video.on')].map(v => v.currentTime)")
    assert all(b > 0 for b in t2)
    assert lab.js("__lab.pool()") >= 16
    assert lab.js("__lab.seed()") > 0


def test_no_external_network(make_lab, server):
    lab = make_lab()
    lab.open()
    lab.page.wait_for_timeout(1500)
    foreign = [u for u in lab.requests if not (u.startswith(server) or u.startswith("data:") or u.startswith("blob:"))]
    assert foreign == []


@pytest.mark.parametrize("vp", VIEWPORTS, ids=lambda v: "%dx%d" % v)
@pytest.mark.parametrize("n", COUNTS)
def test_layout_invariants(make_lab, vp, n):
    lab = make_lab(vp)
    lab.open()
    lab.set_panels(n)
    check_tiling(lab.js(GEOMETRY_JS))
    # exact edge sharing with no overlap
    lab.set("layout.overlap", 0)
    lab.settle()
    check_tiling(lab.js(GEOMETRY_JS), overlap_exact=0)
    assert lab.errors == []


@pytest.mark.parametrize("split", ["equal", "random", "golden", "custom"])
@pytest.mark.parametrize("direction", ["auto", "rows", "columns"])
def test_layout_split_and_direction(make_lab, split, direction):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set("layout.split", split)
    lab.set("layout.direction", direction)
    lab.set_panels(7)
    lab.set("layout.jitter", 30)
    lab.settle(400)
    geo = lab.js(GEOMETRY_JS)
    assert geo["axis"] == ("columns" if direction in ("auto", "columns") else "rows")
    check_tiling(geo)


def test_orientation_follows_viewport_and_resizes_live(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set_panels(6)
    for w, h in [(1280, 720), (375, 812), (320, 320), (2400, 600), (600, 2400), (1000, 1000), (801, 800), (800, 801), (1280, 720)]:
        lab.page.set_viewport_size({"width": w, "height": h})
        lab.page.wait_for_timeout(300)
        geo = lab.js(GEOMETRY_JS)
        assert (geo["W"], geo["H"]) == (w, h)
        assert geo["axis"] == ("columns" if w >= h else "rows")
        check_tiling(geo)


def test_zoom_curve_and_cover(make_lab):
    # framing.mode=center is the zoom module on its own (derived windows add +-jitter around this curve: see test_framing.py)
    lab = make_lab((1280, 720))
    lab.open(values={"framing.mode": "center"})
    prev = math.inf
    for n in [1, 2, 3, 4, 6, 8, 12, 16]:
        lab.set_panels(n)
        z = lab.js("__lab.zoomInfo()")
        expected = max(1, 8 / n ** 0.6)
        assert z["curve"] == pytest.approx(expected, rel=1e-6)
        assert z["curve"] <= prev
        prev = z["curve"]
        assert z["zoom"] >= 1 - 1e-9
        rects = lab.js("__lab.layoutRects()")
        for r in rects:
            assert r["zoom"] >= 1 - 1e-9 and r["zoom"] >= min(expected, 8) - 1e-6
        check_tiling(lab.js(GEOMETRY_JS))
        if n == 1:
            assert z["zoom"] == pytest.approx(8, rel=1e-6)
            assert z["share"] < 0.03, "N=1 must be extremely zoomed in"
            txt = lab.js("document.querySelector('#zoom-readout').textContent")
            assert txt.startswith("zoom 8.00") and "% of the clip visible" in txt, txt
    # user-set curve
    lab.set("zoom.z1", 20)
    lab.set("zoom.gamma", 1.0)
    lab.set_panels(4)
    assert lab.js("__lab.zoomInfo().curve") == pytest.approx(5.0, rel=1e-6)
    lab.set("zoom.manual", 3)
    lab.settle()
    assert lab.js("__lab.zoomInfo().curve") == pytest.approx(3.0, rel=1e-6)
    # floor can never go under cover: crank the gamma
    lab.set("zoom.manual", 0)
    lab.set("zoom.gamma", 2)
    lab.set_panels(16)
    assert lab.js("__lab.zoomInfo().curve") == 1
    check_tiling(lab.js(GEOMETRY_JS))


def test_share_of_clip_visible_shrinks_with_zoom(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set_panels(4)
    lab.set("zoom.manual", 1)
    lab.settle()
    a = lab.js("__lab.zoomInfo().share")
    lab.set("zoom.manual", 10)
    lab.settle()
    b = lab.js("__lab.zoomInfo().share")
    assert b < a / 50
    check_tiling(lab.js(GEOMETRY_JS))


def test_corner_radius_is_zero_by_default_and_settable(lab):
    assert lab.js("getComputedStyle(document.querySelector('.panel')).borderRadius") == "0px"
    lab.set("layout.radius", 24)
    lab.settle(300)
    assert lab.js("getComputedStyle(document.querySelector('.panel')).borderRadius") == "24px"
    check_tiling(lab.js(GEOMETRY_JS))


def test_fixed_seed_gives_the_same_opening_picture(make_lab):
    def opening(seed):
        lab = make_lab((1280, 720))
        lab.open(hash_="")
        lab.set("source.seed", seed)
        lab.page.wait_for_function("(s) => __lab.seed() === s", arg=seed)
        lab.js("__lab.player.sched.reset(0)")
        lab.page.wait_for_timeout(500)
        return lab.js("__lab.scheduled()")
    a, b, c = opening(123), opening(123), opening(124)
    assert a == b and a != c
    l1, l2 = make_lab(), make_lab()
    l1.open(); l2.open()
    assert l1.js("__lab.seed()") > 0 and l2.js("__lab.seed()") > 0
    assert l1.js("__lab.seed()") != l2.js("__lab.seed()"), "seed 0 means a new seed at each page load"
