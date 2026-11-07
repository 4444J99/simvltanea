import json
import subprocess

import pytest

from simvltanea.lab.tests.e2e.helpers import APP_DIR


def registry():
    out = subprocess.run(["node", "-e", "import('%s/params.js').then(m => console.log(JSON.stringify(m.PARAMS)))" % APP_DIR.as_posix()],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


PARAMS = registry()


def drive(lab, p):
    """Operate the real control for parameter p; return the expected value."""
    ctl = lab.page.locator('[data-param="%s"]' % p["id"]).first
    ctl.scroll_into_view_if_needed()
    t, cur = p["type"], lab.js("(i) => __lab.params()[i]", p["id"])
    if t in ("float", "int") and ctl.locator('[role="slider"]').count():
        dial = ctl.locator('[role="slider"]')
        dial.focus()
        key = "Home" if cur == p["max"] else "End"
        dial.press(key)
        want = p["min"] if key == "Home" else p["max"]
        assert dial.get_attribute("aria-valuenow") == str(want)
        # arrow keys move by one step
        dial.press("ArrowRight" if key == "Home" else "ArrowLeft")
        want = round(want + (p["step"] if key == "Home" else -p["step"]), 6)
        return want
    if t == "int":  # plain number input (seed)
        inp = ctl.locator("input")
        inp.fill("4242")
        inp.press("Enter")
        inp.dispatch_event("change")
        return 4242
    if t == "enum":
        other = next(o for o in p["options"] if o != cur)
        ctl.locator("select").select_option(other)
        return other
    if t == "bool":
        ctl.locator('[role="switch"]').click()
        return not cur
    if t == "multi":
        opt = p["options"][0]
        ctl.locator('[data-option="%s"]' % opt).click()
        s = set(cur)
        s.symmetric_difference_update({opt})
        return [o for o in p["options"] if o in s]
    if t == "list":
        inp = ctl.locator("input")
        inp.fill("7, 1" if p["item"] == "number" else "Tree, sky")
        inp.press("Enter")
        return [7, 1] if p["item"] == "number" else ["tree", "sky"]
    raise AssertionError(t)


def test_registry_is_what_the_page_uses(lab):
    ids = lab.js("[...document.querySelectorAll('[data-param]')].map(e => e.dataset.param)")
    for p in PARAMS:
        assert ids.count(p["id"]) == 1, p["id"]
    assert len(PARAMS) >= 70


@pytest.mark.parametrize("p", PARAMS, ids=lambda p: p["id"])
def test_every_parameter_has_a_working_control(lab, p):
    ctl = lab.page.locator('[data-param="%s"]' % p["id"])
    assert ctl.count() == 1
    assert p["description"] in ctl.first.get_attribute("title"), "tooltip comes from the registry"
    want = drive(lab, p)
    got = lab.js("(i) => __lab.params()[i]", p["id"])
    if isinstance(want, float):
        assert got == pytest.approx(want, abs=1e-6)
    else:
        assert got == want
    # the engine (frame loop snapshot) sees it too
    lab.page.wait_for_function("([i, w]) => JSON.stringify(__lab.effective()[i]) === JSON.stringify(__lab.params()[i])", arg=[p["id"], got], timeout=3000)
    # controls show the state back
    if p["type"] == "bool":
        assert ctl.locator('[role="switch"]').get_attribute("aria-checked") == str(want).lower()
    if p["modulatable"]:
        assert ctl.locator(".modbtn").count() == 1
    if p["randomizable"]:
        assert ctl.locator(".lockbtn").count() == 1
    assert lab.errors == [] or all("Failed to load resource" in e for e in lab.errors), lab.errors


def test_mod_toggle_makes_the_engine_value_breathe(lab):
    ctl = lab.page.locator('[data-param="relation.strength"]')
    ctl.locator(".modbtn").click()
    assert lab.js("__lab.config().mods['relation.strength'].on") is True
    assert ctl.locator(".modrow").is_visible() or lab.page.locator('[data-param="relation.strength"] ~ .modrow').first.is_visible()
    lab.js("__lab.store.mod('relation.strength', {rate: 3, depth: 1, shape: 'triangle'})")
    seen = set()
    for _ in range(12):
        seen.add(round(lab.js("__lab.effective()['relation.strength']"), 2))
        lab.page.wait_for_timeout(70)
    assert len(seen) > 4 and min(seen) >= -4 and max(seen) <= 4
    assert lab.js("__lab.params()['relation.strength']") == 0, "base value unchanged by modulation"
    for shape in ("sine", "random", "square"):
        lab.js("(s) => __lab.store.mod('relation.strength', {shape: s})", shape)
    lab.js("__lab.store.mod('relation.strength', {on: false})")
    lab.page.wait_for_timeout(200)
    assert lab.js("__lab.effective()['relation.strength']") == 0


def test_bypass_reset_and_collapse(lab):
    lab.set("zoom.z1", 20)
    lab.settle()
    assert lab.js("__lab.zoomInfo().curve") == pytest.approx(20 / 4 ** 0.6, rel=1e-3)
    card = lab.page.locator('[data-module="zoom"]')
    card.locator(".byp").click()
    lab.page.wait_for_timeout(200)
    assert lab.js("__lab.effective()['zoom.z1']") == 8 and lab.js("__lab.params()['zoom.z1']") == 20
    card.locator(".byp").click()
    lab.page.wait_for_timeout(200)
    assert lab.js("__lab.effective()['zoom.z1']") == 20
    card.locator(".rst").click()
    assert lab.js("__lab.params()['zoom.z1']") == 8
    card.locator(".mod-title").click()
    assert not card.locator(".mod-body").is_visible()
    assert card.locator(".mod-title").get_attribute("aria-expanded") == "false"
    card.locator(".mod-title").click()
    assert card.locator(".mod-body").is_visible()


def test_knob_keyboard_wheel_drag_and_typed_value(lab):
    dial = lab.page.locator('[data-param="zoom.z1"] [role="slider"]')
    dial.focus()
    assert dial.get_attribute("aria-label") == "Z1 (zoom at one panel)"
    assert dial.get_attribute("aria-valuemin") == "1" and dial.get_attribute("aria-valuemax") == "40"
    dial.press("ArrowUp")
    assert lab.js("__lab.params()['zoom.z1']") == pytest.approx(8.1)
    dial.press("Shift+ArrowUp")
    assert lab.js("__lab.params()['zoom.z1']") == pytest.approx(9.1)
    dial.press("PageDown")
    assert lab.js("__lab.params()['zoom.z1']") < 9.1
    dial.press("Home")
    assert lab.js("__lab.params()['zoom.z1']") == 1
    assert dial.get_attribute("aria-valuetext") == "1.0 x"
    dial.hover()
    lab.page.mouse.wheel(0, -100)
    lab.page.wait_for_timeout(100)
    assert lab.js("__lab.params()['zoom.z1']") == pytest.approx(1.1)
    box = dial.bounding_box()
    lab.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    lab.page.mouse.down()
    lab.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2 - 90, steps=6)
    lab.page.mouse.up()
    dragged = lab.js("__lab.params()['zoom.z1']")
    assert 15 < dragged < 25, dragged
    dial.dblclick()
    inp = lab.page.locator('[data-param="zoom.z1"] input.val-edit')
    assert inp.is_visible()
    inp.fill("5.5")
    inp.press("Enter")
    assert lab.js("__lab.params()['zoom.z1']") == pytest.approx(5.5)
    dial.dblclick()
    lab.page.locator('[data-param="zoom.z1"] input.val-edit').fill("999")
    lab.page.keyboard.press("Enter")
    assert lab.js("__lab.params()['zoom.z1']") == 40
    dial.dblclick()
    lab.page.locator('[data-param="zoom.z1"] input.val-edit').fill("3")
    lab.page.keyboard.press("Escape")
    assert lab.js("__lab.params()['zoom.z1']") == 40


def test_signed_relation_knob_is_bipolar(lab):
    dial = lab.page.locator('[data-param="relation.strength"] [role="slider"]')
    dial.focus()
    dial.press("Home")
    assert lab.js("__lab.params()['relation.strength']") == -4
    dial.press("End")
    assert lab.js("__lab.params()['relation.strength']") == 4


def test_randomize_respects_locks_and_source(lab):
    lab.page.locator('[data-param="zoom.gamma"] .lockbtn').click()
    assert lab.js("__lab.config().locks.includes('zoom.gamma')")
    before = lab.js("__lab.params()")
    changed = 0
    for _ in range(3):
        lab.page.click("#btn-randomize")
        after = lab.js("__lab.params()")
        assert after["zoom.gamma"] == before["zoom.gamma"]
        for k in after:
            if k.startswith("source.") or k in ("audio.master", "audio.limiter", "audio.limiter_ceiling"):
                assert after[k] == before[k], k
        changed += sum(1 for k in after if after[k] != before[k])
        assert 1 <= after["layout.panels"] <= 16
    assert changed > 20
    lab.page.wait_for_function("document.querySelectorAll('.panel').length === __lab.params()['layout.panels']")
    lab.page.click("#btn-reset-all")
    assert lab.js("__lab.params()['layout.panels']") == 4
    assert lab.js("__lab.params()['zoom.gamma']") == 0.6
