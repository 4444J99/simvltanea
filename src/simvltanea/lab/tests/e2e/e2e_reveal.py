import pytest


def tap(lab, k=0):
    lab.page.keyboard.press("h")
    lab.page.locator('.panel[data-panel="%d"]' % k).click(position={"x": 8, "y": 8})


@pytest.mark.parametrize("has_date", [True, False])
def test_tap_opens_still_with_date_and_tags_and_escape_closes(make_lab, clips, has_date):
    clip = next(c for c in clips.values() if "tags" in c and ("captured_at" in c) == has_date)
    lab = make_lab()
    lab.page.route("**/data/clips.json", lambda route: route.fulfill(json={"version": 1, "clips": [clip]}))
    lab.open(values={"layout.panels": 1})
    ids = lab.js("__lab.engine()")
    tap(lab)
    lab.page.wait_for_selector(".reveal img.reveal-still")
    cid = lab.js("__lab.reveal().clip")
    assert cid == ids[0] == clip["id"]
    src = lab.page.locator(".reveal img.reveal-still").get_attribute("src")
    assert src.endswith(clips[cid]["still"])
    lab.page.wait_for_function("document.querySelector('.reveal img').complete && document.querySelector('.reveal img').naturalWidth > 0")
    date = lab.page.locator(".reveal-date").text_content()
    if has_date:
        assert clip["captured_at"][:4] in date
    else:
        assert date == "date unknown"
    chips = lab.page.locator(".reveal .chip").all_text_contents()
    assert clips[cid]["tags"]["subjects"][0] in chips
    assert lab.js("__lab.reveal().open") is True
    lab.page.wait_for_timeout(500)
    box = lab.page.locator(".reveal").bounding_box()
    assert (box["x"], box["y"], box["width"], box["height"]) == (0, 0, 1280, 720)
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    assert lab.js("__lab.reveal().open") is False
    assert lab.errors == []


def test_enter_on_focused_panel_opens_and_click_closes(lab):
    lab.page.locator('.panel[data-panel="0"]').focus()
    lab.page.keyboard.press("Enter")
    lab.page.wait_for_selector(".reveal")
    assert lab.page.locator(".reveal").get_attribute("role") == "dialog"
    lab.page.wait_for_timeout(450)
    lab.page.mouse.click(640, 360)
    lab.page.wait_for_selector(".reveal", state="detached")


def test_reveal_animates_from_the_panel_rectangle(lab):
    lab.js("__lab.set('reveal.anim_ms', 1000)")
    lab.page.keyboard.press("h")
    lab.page.locator('.panel[data-panel="2"]').click(position={"x": 8, "y": 8})
    lab.page.wait_for_selector(".reveal")
    clip = lab.page.locator(".reveal").evaluate("e => getComputedStyle(e).clipPath")
    assert clip.startswith("inset(") and clip != "inset(0px)"
    lab.page.wait_for_timeout(1200)
    assert lab.page.locator(".reveal").evaluate("e => getComputedStyle(e).clipPath") in ("inset(0px)", "inset(0px 0px 0px 0px)")


def test_actions_video_both_and_toggles(lab, clips):
    lab.set("reveal.action", "video")
    lab.set("reveal.show_tags", False)
    lab.set("reveal.show_date", True)
    tap(lab, 0)
    lab.page.wait_for_selector(".reveal video.reveal-video")
    assert lab.page.locator(".reveal img.reveal-still").count() == 0
    assert lab.page.locator(".reveal .chip").count() == 0
    assert lab.page.locator(".reveal-date").count() == 1
    lab.page.wait_for_function("document.querySelector('.reveal video').readyState >= 2")
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    lab.set("reveal.action", "both")
    lab.set("reveal.show_tags", True)
    lab.set("reveal.show_date", False)
    lab.page.locator('.panel[data-panel="0"]').click(position={"x": 8, "y": 8})
    lab.page.wait_for_selector(".reveal img.reveal-still")
    assert lab.page.locator(".reveal video.reveal-video.inset").count() == 1
    assert lab.page.locator(".reveal .chip").count() > 0
    assert lab.page.locator(".reveal-date").count() == 0


def test_pause_others_only_when_configured(lab):
    def playing():
        return lab.js("[...document.querySelectorAll('.panel video.on')].filter(v => !v.paused).length")
    lab.page.wait_for_timeout(500)
    assert playing() >= 4
    tap(lab, 0)
    lab.page.wait_for_selector(".reveal")
    lab.page.wait_for_timeout(300)
    assert playing() >= 4, "others keep playing by default"
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    lab.set("reveal.pause_others", True)
    lab.page.locator('.panel[data-panel="0"]').click(position={"x": 8, "y": 8})
    lab.page.wait_for_selector(".reveal")
    lab.page.wait_for_timeout(300)
    assert playing() == 0
    lab.page.keyboard.press("Escape")
    lab.page.wait_for_selector(".reveal", state="detached")
    lab.page.wait_for_timeout(300)
    assert playing() >= 4


def test_space_toggles_global_pause(lab):
    lab.page.wait_for_timeout(400)
    lab.page.keyboard.press("Space")
    lab.page.wait_for_timeout(200)
    assert lab.js("__lab.paused()") is True
    assert lab.js("[...document.querySelectorAll('.panel video.on')].every(v => v.paused)")
    t0 = lab.js("__lab.player.t")
    lab.page.wait_for_timeout(500)
    assert lab.js("__lab.player.t") == t0, "scheduler clock is frozen while paused"
    assert lab.page.locator("#btn-pause").text_content() == "Play"
    lab.page.keyboard.press("Space")
    lab.page.wait_for_timeout(300)
    assert lab.js("__lab.paused()") is False
    assert lab.js("[...document.querySelectorAll('.panel video.on')].some(v => !v.paused)")
    # Space on a focused panel also pauses (it does not open the reveal)
    lab.page.locator('.panel[data-panel="0"]').focus()
    lab.page.keyboard.press("Space")
    assert lab.js("__lab.paused()") is True and lab.js("__lab.reveal().open") is False
    lab.page.keyboard.press("Space")
    # Space on a switch toggles the switch, not the transport
    sw = lab.page.locator('[data-param="path.wrap"] [role="switch"]')
    before = lab.js("__lab.params()['path.wrap']")
    sw.focus()
    lab.page.keyboard.press("Space")
    assert lab.js("__lab.params()['path.wrap']") != before and lab.js("__lab.paused()") is False


@pytest.mark.parametrize("action", ["still", "both"])
def test_missing_still_uses_full_video(make_lab, clips, action):
    clip = dict(next(iter(clips.values())), still="")
    lab = make_lab()
    lab.page.route("**/data/clips.json", lambda route: route.fulfill(json={"version": 1, "clips": [clip]}))
    lab.open(values={"layout.panels": 1, "reveal.action": action})
    tap(lab)
    video = lab.page.locator(".reveal video.reveal-video")
    assert video.count() == 1
    assert video.get_attribute("src").endswith(clip["video"])
    assert lab.page.locator(".reveal .inset, .reveal img").count() == 0


def test_pause_controls_reveal_video_and_respects_pause_others(make_lab):
    lab = make_lab()
    lab.open(values={"reveal.action": "video", "reveal.pause_others": True})
    lab.page.keyboard.press("Space")
    tap(lab)
    lab.page.wait_for_function("document.querySelector('.reveal video')?.readyState >= 2")
    assert lab.js("document.querySelector('.reveal video').paused")
    lab.page.keyboard.press("Space")
    lab.page.wait_for_function("!document.querySelector('.reveal video').paused")
    assert lab.js("[...document.querySelectorAll('.panel video')].every(v => v.paused)")
    lab.page.keyboard.press("Space")
    assert lab.js("document.querySelector('.reveal video').paused")
