import statistics

import pytest

from simvltanea.lab.tests.e2e.helpers import GEOMETRY_JS, check_tiling

FRAMING_IDS = ["framing.mode", "framing.spread", "framing.zoom_jitter", "framing.candidates", "framing.temperature",
               "framing.neighbour_influence", "framing.edge_sample", "framing.match_on", "framing.vary_per_appearance",
               "framing.memory", "framing.drift_speed"]
MODES = ["center", "random", "thirds", "detail", "blend", "contrast", "drift"]
FASTCLIPS = {"timing.hold_min": 0.5, "timing.hold_max": 0.8, "timing.cooldown": 0, "timing.stagger": 0}

DOM_WINDOWS = """() => [...document.querySelectorAll('.panel')].map((p) => {
  const pr = p.getBoundingClientRect();
  const v = [...p.querySelectorAll('video.on')].filter((x) => x.getAttribute('src')).pop();
  const vr = v.getBoundingClientRect();
  return {x0: (pr.x - vr.x) / vr.width, x1: (pr.x + pr.width - vr.x) / vr.width, y0: (pr.y - vr.y) / vr.height, y1: (pr.y + pr.height - vr.y) / vr.height};
})"""


def windows(lab):
    return lab.js("__lab.framing()")


def inside(a, eps=1e-6):
    return a["x0"] >= -eps and a["y0"] >= -eps and a["x1"] <= 1 + eps and a["y1"] <= 1 + eps


def test_every_framing_parameter_is_a_control_in_the_framing_module_and_in_the_registry(lab):
    reg = lab.js("(async () => { const m = await import('./params.js'); return m.PARAMS.filter((p) => p.module === 'framing').map((p) => p.id); })()")
    assert reg == FRAMING_IDS
    for pid in FRAMING_IDS + ["reveal.show_window", "audio.speech_policy", "audio.mute_unscreened"]:
        loc = lab.page.locator('[data-param="%s"]' % pid)
        assert loc.count() == 1, pid
        assert lab.page.locator('.module[data-module="framing"] [data-param="%s"]' % pid).count() == (1 if pid.startswith("framing.") else 0)
        assert loc.get_attribute("title"), pid + " has a tooltip"
    assert lab.page.locator('[data-param="framing.mode"] select option').all_text_contents() == MODES
    assert lab.page.locator('.module[data-module="framing"] .mod-title').count() == 1


def test_framing_controls_drive_the_parameters(lab):
    lab.page.select_option("#in-framing-mode", "thirds")
    assert lab.js("__lab.params()['framing.mode']") == "thirds"
    lab.page.select_option("#in-framing-match_on", "luma")
    assert lab.js("__lab.params()['framing.match_on']") == "luma"
    sw = lab.page.locator('[data-param="framing.vary_per_appearance"] [role=switch]')
    assert sw.get_attribute("aria-checked") == "true"
    sw.click()
    assert lab.js("__lab.params()['framing.vary_per_appearance']") is False
    dial = lab.page.locator('[data-param="framing.spread"] [role="slider"]')
    dial.focus(); dial.press("Home")
    assert lab.js("__lab.params()['framing.spread']") == 0
    dial.press("End")
    assert lab.js("__lab.params()['framing.spread']") == 1
    mem = lab.page.locator('[data-param="framing.memory"] [role="slider"]')
    mem.focus(); mem.press("End")
    assert lab.js("__lab.params()['framing.memory']") == 32
    # a float knob can be modulated, a randomize press never leaves the registry range
    assert lab.page.locator('[data-param="framing.spread"] .modbtn').count() == 1
    for _ in range(3):
        lab.page.click("#btn-randomize")
        p = lab.js("__lab.params()")
        assert p["framing.mode"] in MODES and 0 <= p["framing.spread"] <= 1 and 1 <= p["framing.memory"] <= 32


def test_framing_parameters_round_trip_through_patches_and_the_share_url(make_lab):
    a = make_lab()
    a.open()
    odd = {"framing.mode": "contrast", "framing.spread": 0.37, "framing.zoom_jitter": 33, "framing.candidates": 77, "framing.temperature": 0.55,
           "framing.neighbour_influence": 0.42, "framing.edge_sample": 0.21, "framing.match_on": "hue", "framing.vary_per_appearance": False,
           "framing.memory": 11, "framing.drift_speed": 7.5, "reveal.show_window": True, "audio.speech_policy": "exclude", "audio.mute_unscreened": False}
    for k, v in odd.items():
        a.set(k, v)
    a.page.fill("#patch-name", "framed")
    a.page.click("#patch-save")
    a.page.click("#btn-reset-all")
    assert a.js("__lab.params()['framing.mode']") == "blend" and a.js("__lab.params()['audio.speech_policy']") == "mute"
    a.page.locator("#patch-list").select_option("framed")
    a.page.click("#patch-load")
    got = a.js("__lab.params()")
    for k, v in odd.items():
        assert got[k] == v, k
    a.page.click("#patch-share")
    url = a.page.locator("#share-url").input_value()
    b = make_lab()
    b.page.goto(url)
    b.ready()
    got = b.js("__lab.params()")
    for k, v in odd.items():
        assert got[k] == v, k
    assert b.js("__lab.config()") == a.js("__lab.config()")


def test_grid8_fixtures_and_fallbacks(lab, clips):
    n_grid = sum(1 for c in clips.values() if len(c.get("features", {}).get("grid8", "")) == 384)
    assert n_grid >= 18
    kinds = lab.js("""(async () => { const f = await import('./framing.js'); const r = __lab.player.records;
      return Object.fromEntries(r.map((x) => [x.id, f.colourOf(x).kind])); })()""")
    by = {cid: kinds[cid] for cid in clips}
    assert list(by.values()).count("grid8") == n_grid
    assert "palette" in by.values() and "none" in by.values(), by


def test_every_mode_covers_every_strip_inside_the_source_no_gaps_no_errors(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set_panels(6)
    for mode in MODES:
        lab.page.select_option("#in-framing-mode", mode)
        lab.settle(500)
        geo = lab.js(GEOMETRY_JS)
        check_tiling(geo)
        fr = windows(lab)
        assert len(fr) == 6 and all(w["window"] for w in fr)
        for w in fr:
            assert inside(w["applied"]), (mode, w)
            assert w["requested"] == mode
        dom = lab.js(DOM_WINDOWS)
        for w, d in zip(fr, dom):
            for k in ("x0", "x1", "y0", "y1"):
                assert w["applied"][k] == pytest.approx(d[k], abs=0.01), (mode, k, w["applied"], d)
    assert lab.errors == []


def test_mode_changes_apply_the_geometry_numerically_across_viewports_and_panel_counts(make_lab):
    for viewport in [(1280, 720), (390, 844), (900, 900)]:
        lab = make_lab(viewport)
        lab.open()
        for n in (1, 3, 12, 16):
            lab.set_panels(n)
            for mode in ("random", "thirds", "blend", "drift"):
                lab.set("framing.mode", mode)
                lab.settle(250)
                check_tiling(lab.js(GEOMETRY_JS))
                for w in windows(lab):
                    assert inside(w["applied"]), (viewport, n, mode)
                    assert w["applied"]["zoom"] >= 1 - 1e-9
        assert lab.errors == []


def test_switching_mode_live_changes_the_windows_and_center_equals_the_zoom_module(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set("timing.hold_min", 60); lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.set_panels(5)
    lab.settle(800)
    ids = lab.js("__lab.engine()")
    by_mode = {}
    for mode in ["center", "random", "thirds", "detail", "blend", "contrast"]:
        lab.page.select_option("#in-framing-mode", mode)
        lab.settle(400)
        assert lab.js("__lab.engine()") == ids, "switching the framing mode never changes which clips play"
        by_mode[mode] = [(round(w["applied"]["cx"], 3), round(w["applied"]["cy"], 3), round(w["applied"]["zoom"], 2)) for w in windows(lab)]
    modes = list(by_mode)
    for i, a in enumerate(modes):
        for b in modes[i + 1:]:
            assert by_mode[a] != by_mode[b], (a, b)
    # center: exactly the old behaviour: zoom = curve, focal = layout.focalPoint(static) for panel:clip
    lab.page.select_option("#in-framing-mode", "center")
    lab.settle(400)
    expect = lab.js("""(async () => { const L = await import('./layout.js'); const P = __lab.player;
      return P.panels.map((p) => { const r = p.rect, s = p.slots[p.active];
        const e = P.eff, z = L.zoomFor(P.panels.length, {z1: e['zoom.z1'], gamma: e['zoom.gamma'], floor: e['zoom.floor'], manual: e['zoom.manual']});
        const f = L.focalPoint('static', p.k + ':' + s.rec.id, 0, 0);
        const fit = L.fitVideo({cw: r.w, ch: r.h, vw: s.vw, vh: s.vh, zoom: z, focal: f, axis: P.layout.axis, jitterAmp: e['layout.jitter'], jitterNow: 0});
        return {scale: fit.scale, tx: fit.tx, ty: fit.ty, key: p.k}; }); })()""")
    got = lab.js("""[...document.querySelectorAll('.panel')].map((p) => { const t = [...p.querySelectorAll('video.on')].filter((x) => x.getAttribute('src')).pop().style.transform;
      const m = /translate\\((-?[\\d.]+)px,\\s*(-?[\\d.]+)px\\) scale\\(([\\d.]+)\\)/.exec(t); return {tx: +m[1], ty: +m[2], scale: +m[3]}; })""")
    for e, g in zip(expect, got):
        assert g["tx"] == pytest.approx(e["tx"], abs=0.006) and g["ty"] == pytest.approx(e["ty"], abs=0.006) and g["scale"] == pytest.approx(e["scale"], abs=1e-5), (e, g)
    assert lab.errors == []


def collect(lab, seconds, every=0.12):
    """Poll __lab.framing(): {(clip, appearance): window} and the facing-edge mismatches seen."""
    seen, mism = {}, {}
    end = lab.js("performance.now()") + seconds * 1000
    while lab.js("performance.now()") < end:
        for w in windows(lab):
            if w["clip"] is None or w["appearance"] is None:
                continue
            key = (w["clip"], w["appearance"])
            seen.setdefault(key, (round(w["window"]["cx"], 4), round(w["window"]["cy"], 4), round(w["window"]["zoom"], 3)))
            if w["edgeMismatch"] is not None:
                mism.setdefault(key + (w["panel"],), w["edgeMismatch"])
        lab.page.wait_for_timeout(int(every * 1000))
    return seen, mism


def test_the_same_clip_is_framed_differently_each_time_it_appears(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    for k, v in FASTCLIPS.items():
        lab.set(k, v)
    lab.set("source.tags_include", ["nature"])      # a small pool: every clip comes round again quickly
    lab.set("framing.mode", "random")
    lab.set("framing.zoom_jitter", 0)
    lab.set_panels(2)
    seen, _ = collect(lab, 14)
    per_clip = {}
    for (cid, app), win in seen.items():
        per_clip.setdefault(cid, {})[app] = win
    repeated = {c: a for c, a in per_clip.items() if len(a) >= 3}
    assert repeated, "no clip appeared three times: %s" % {c: len(a) for c, a in per_clip.items()}
    for cid, apps in repeated.items():
        assert len(set(apps.values())) == len(apps), (cid, apps)
    # with variation off the same clip is cropped identically every time
    lab.set("framing.vary_per_appearance", False)
    lab.settle(300)
    seen2, _ = collect(lab, 8)
    again = {}
    for (cid, app), win in seen2.items():
        again.setdefault(cid, set()).add(win)
    assert again
    for cid, wins in again.items():     # (panels differ by a few px of overlap, hence the small tolerance)
        for w in wins:
            assert all(abs(a - b) < 0.005 for a, b in zip(w, next(iter(wins)))), (cid, wins)
    assert any(len(v) >= 1 for v in again.values())
    assert lab.errors == []


def test_blend_lowers_and_contrast_raises_the_on_screen_edge_mismatch(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    for k, v in FASTCLIPS.items():
        lab.set(k, v)
    lab.set("framing.neighbour_influence", 1)
    lab.set("framing.temperature", 0.05)
    lab.set("framing.zoom_jitter", 0)
    lab.set_panels(5)
    means = {}
    for mode in ("random", "blend", "contrast"):
        lab.set("framing.mode", mode)
        lab.settle(300)
        _, mism = collect(lab, 12)
        vals = [v for (cid, app, panel), v in mism.items() if panel > 0]
        assert len(vals) >= 25, (mode, len(vals))
        means[mode] = statistics.mean(vals)
    print(means)
    assert means["blend"] < means["random"] * 0.9, means
    assert means["contrast"] > means["random"] * 1.1, means
    assert lab.errors == []


def test_a_window_depends_on_the_neighbour(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set("framing.mode", "blend")
    lab.set("framing.temperature", 0)
    lab.set("framing.neighbour_influence", 1)
    lab.set("framing.zoom_jitter", 0)
    out = lab.js("""(async () => {
      const f = await import('./framing.js'); const P = __lab.player;
      const p = P.panels[2], s = p.slots[p.active], r = p.rect;
      // Hermetic grids: the decoded fixture frames differ between FFmpeg builds, the claim under test does not.
      const hex = (n) => n.toString(16).padStart(2, '0');
      const gradient = Array.from({length: 64}, (_, i) => hex((i % 8) * 32) + hex(Math.floor(i / 8) * 32) + hex(128)).join('');
      const flat = (k) => Array.from({length: 64}, () => hex((k * 53) % 256) + hex((k * 97) % 256) + hex((k * 29) % 256)).join('');
      const own = {...s.rec, features: {...s.rec.features, grid8: gradient}};
      const ctx = {srcAspect: s.vw / s.vh, cellAspect: r.w / r.h};
      const params = f.framingParams({...__lab.effective(), 'framing.mode': 'blend', 'framing.temperature': 0, 'framing.neighbour_influence': 1, 'framing.zoom_jitter': 0});
      const wins = [];
      for (const other of [3, 4, 5, 6, 7, 8]) {
        const nb = {dir: -1, win: {cx: 0.5, cy: 0.5, zoom: 4}, clip: {...P.records[other], features: {...P.records[other].features, grid8: flat(other)}}, srcAspect: 0.75, cellAspect: r.w / r.h};
        wins.push(f.deriveWindow({clip: own, ...ctx, baseZoom: 4, seed: 1, neighbours: [nb], params}));
      }
      return wins.map((w) => [w.cx.toFixed(3), w.cy.toFixed(3)].join(','));
    })()""")
    assert len(set(out)) >= 3, out


def test_drift_moves_during_the_hold_and_freezes_under_reduced_motion(make_lab):
    lab = make_lab((1280, 720), reduced_motion="no-preference")
    lab.open()
    lab.set("timing.hold_min", 60); lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.set("framing.mode", "drift")
    lab.set("framing.drift_speed", 30)       # one leg per second
    lab.set("framing.zoom_jitter", 30)
    lab.set("framing.spread", 1)
    lab.set_panels(3)
    lab.settle(500)
    track = []
    for _ in range(10):
        track.append([(w["applied"]["cx"], w["applied"]["cy"], w["applied"]["zoom"]) for w in windows(lab)])
        check_tiling(lab.js(GEOMETRY_JS))
        lab.page.wait_for_timeout(250)
    for k in range(3):
        pts = [t[k] for t in track]
        assert max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(pts, pts[1:])) > 0.01, "panel %d drifts" % k
        assert len(set(pts)) >= 8
    lab.page.emulate_media(reduced_motion="reduce")
    lab.settle(400)
    a = [w["applied"] for w in windows(lab)]
    lab.page.wait_for_timeout(1500)
    b = [w["applied"] for w in windows(lab)]
    assert a == b, "reduced motion: the drift path stands still"
    assert lab.errors == []


def test_reveal_outlines_the_derived_window_on_the_full_still(make_lab):
    lab = make_lab((1280, 720))
    lab.open()
    lab.set("reveal.show_window", True)
    lab.set("reveal.animation", "none")
    lab.set("timing.hold_min", 60); lab.set("timing.hold_max", 120)
    lab.js("__lab.player.sched.reset(__lab.player.t)")
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.set("framing.zoom_jitter", 0)
    lab.settle(800)
    lab.page.locator('.panel[data-panel="1"]').click(position={"x": 20, "y": 20})
    lab.page.wait_for_selector(".reveal-window")
    lab.page.wait_for_function("document.querySelector('.reveal img').complete && document.querySelector('.reveal-window').dataset.window")
    lab.settle(200)
    fr = windows(lab)[1]
    box = lab.js("""(() => { const b = document.querySelector('.reveal-window').getBoundingClientRect(), i = document.querySelector('.reveal img'), n = {w: i.naturalWidth, h: i.naturalHeight};
      const s = document.querySelector('.reveal-stage').getBoundingClientRect(), k = Math.min(s.width / n.w, s.height / n.h), iw = n.w * k, ih = n.h * k, ox = s.x + (s.width - iw) / 2, oy = s.y + (s.height - ih) / 2;
      return {x0: (b.x - ox) / iw, y0: (b.y - oy) / ih, x1: (b.x + b.width - ox) / iw, y1: (b.y + b.height - oy) / ih, bw: b.width, bh: b.height}; })()""")
    a = fr["applied"]
    for k in ("x0", "y0", "x1", "y1"):
        assert box[k] == pytest.approx(a[k], abs=0.01), (k, box, a)
    rect = lab.js("__lab.layoutRects()[1]")
    assert box["bw"] / box["bh"] == pytest.approx(rect["w"] / rect["h"], rel=0.02), "the outline has the strip's shape"
    assert inside(box, 0.01)
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    lab.set("reveal.show_window", False)
    lab.page.locator('.panel[data-panel="1"]').click(position={"x": 20, "y": 20})
    lab.page.wait_for_selector(".reveal img.reveal-still")
    assert lab.page.locator(".reveal-window").count() == 0
    assert lab.errors == []
