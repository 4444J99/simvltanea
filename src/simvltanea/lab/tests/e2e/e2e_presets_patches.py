import json
import os
import tempfile

import pytest

from simvltanea.lab.tests.e2e.helpers import APP_DIR

PRESET_IDS = None


def preset_ids():
    import subprocess
    out = subprocess.run(["node", "-e", "import('%s/presets.js').then(m => console.log(JSON.stringify(m.PRESETS.map(p => [p.id, p.values, p.resets]))))" % APP_DIR.as_posix()],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


PRESETS = preset_ids()


@pytest.mark.parametrize("pid,values,resets", PRESETS, ids=[p[0] for p in PRESETS])
def test_presets_switch_live(lab, pid, values, resets):
    lab.set("audio.master", 1.1)
    lab.page.locator("#preset-select").select_option(pid)
    params = lab.js("__lab.params()")
    for k, v in values.items():
        assert params[k] == v, k
    assert params["audio.master"] == 1.1, "presets leave audio alone"
    lab.page.wait_for_function("__lab.engine().every(Boolean)")
    lab.page.wait_for_timeout(500)
    ids = lab.js("__lab.engine()")
    n = params["layout.panels"]
    assert len(ids) == n and all(ids) and len(set(ids)) == n
    assert lab.page.locator("#preset-select").input_value() == pid
    assert lab.errors == []


def test_editing_a_core_param_marks_the_preset_custom(lab):
    lab.page.locator("#preset-select").select_option("chronological")
    assert lab.page.locator("#preset-desc").text_content() != ""
    lab.set("timing.novelty", 0.9)
    assert lab.page.locator("#preset-select").input_value() == ""


def test_converge_scene_puts_oldest_and_newest_on_screen(lab):
    lab.page.locator("#preset-select").select_option("scene_triptych_time")
    lab.page.wait_for_function("document.querySelectorAll('.panel').length === 3")
    lab.page.wait_for_timeout(400)
    pos = lab.js("(() => { const s = __lab.player.sched; return {pos: s.panels.map((p) => s.posOf[p.clip]), L: s.order.length, n: s.panels.map((p) => p.n)}; })()")
    L = pos["L"]
    assert L >= 16 and pos["n"] == [1, 1, 1]
    assert pos["pos"][0] <= 2, pos            # panel 1 walks in from the oldest end
    assert pos["pos"][1] >= L - 3, pos        # panel 2 walks in from the newest end
    ids = lab.js("__lab.engine()")
    assert len(set(ids)) == 3


def test_patch_save_load_delete(lab):
    lab.set("layout.panels", 7)
    lab.set("zoom.z1", 11)
    lab.js("__lab.store.mod('zoom.gamma', {on: true, shape: 'square', rate: 0.5, depth: 0.3})")
    lab.page.fill("#patch-name", "my patch")
    lab.page.click("#patch-save")
    assert lab.js("Object.keys(JSON.parse(localStorage.getItem('lab.patches.v1')))") == ["my patch"]
    lab.set("layout.panels", 2)
    lab.set("zoom.z1", 3)
    lab.js("__lab.store.mod('zoom.gamma', {on: false})")
    lab.page.locator("#patch-list").select_option("my patch")
    lab.page.click("#patch-load")
    p = lab.js("__lab.params()")
    assert p["layout.panels"] == 7 and p["zoom.z1"] == 11
    assert lab.js("__lab.config().mods['zoom.gamma']") == {"on": True, "shape": "square", "rate": 0.5, "depth": 0.3}
    lab.page.wait_for_function("document.querySelectorAll('.panel').length === 7")
    # survives a reload (localStorage)
    lab.open()
    assert lab.page.locator("#patch-list option").count() == 2
    lab.page.locator("#patch-list").select_option("my patch")
    lab.page.click("#patch-delete")
    assert lab.page.locator("#patch-list option").count() == 1


def test_save_needs_a_name(lab):
    lab.page.click("#patch-save")
    assert "name" in lab.page.locator("#toast").text_content().lower()
    assert lab.js("localStorage.getItem('lab.patches.v1')") is None


def test_export_and_import_json(lab):
    lab.set("layout.panels", 9)
    lab.set("path.shape", "pingpong")
    lab.set("source.tags_exclude", ["tree"])
    lab.page.fill("#patch-name", "exp")
    with lab.page.expect_download() as dl:
        lab.page.click("#patch-export")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert data["app"] == "lab" and data["config"]["values"]["layout.panels"] == 9
    assert dl.value.suggested_filename == "exp.lab.json"
    lab.page.click("#btn-reset-all")
    assert lab.js("__lab.params()['layout.panels']") == 4
    lab.page.set_input_files("#patch-import", path)
    lab.page.wait_for_function("__lab.params()['layout.panels'] === 9")
    p = lab.js("__lab.params()")
    assert p["path.shape"] == "pingpong" and p["source.tags_exclude"] == ["tree"]
    # a hand-edited / hostile file is sanitised, a non-patch is rejected
    data["config"]["values"]["zoom.z1"] = 9999
    data["config"]["values"]["path.shape"] = "nonsense"
    data["config"]["values"]["bogus"] = 1
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(data, f)
    lab.page.set_input_files("#patch-import", f.name)
    lab.page.wait_for_function("__lab.params()['zoom.z1'] === 40")
    assert lab.js("__lab.params()['path.shape']") == "random"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as g:
        g.write("[1,2,3]")
    lab.page.set_input_files("#patch-import", g.name)
    lab.page.wait_for_function("document.querySelector('#toast').textContent.startsWith('Import failed')")
    for n in (f.name, g.name):
        os.unlink(n)


def test_share_url_round_trips_whole_configuration(make_lab):
    a = make_lab()
    a.open()
    a.set("layout.panels", 11)
    a.set("order.axis", "hue")
    a.set("path.shape", "converge")
    a.set("relation.strength", -2.5)
    a.set("source.tags_include", ["nature", "sky"])
    a.set("audio.muted_panels", [2, 3])
    a.js("__lab.store.mod('zoom.z1', {on: true, shape: 'triangle', rate: 0.7, depth: 0.4})")
    a.js("__lab.store.lock('zoom.gamma', true)")
    a.js("__lab.store.bypass('reveal', true)")
    a.page.click("#patch-share")
    url = a.page.locator("#share-url").input_value()
    assert "#p=" in url and "data=" in url
    want = a.js("__lab.config()")
    b = make_lab()
    b.page.goto(url)
    b.ready()
    assert b.js("__lab.config()") == want
    b.page.wait_for_function("document.querySelectorAll('.panel').length === 11")
    assert b.js("document.querySelectorAll('.panel').length") == 11
