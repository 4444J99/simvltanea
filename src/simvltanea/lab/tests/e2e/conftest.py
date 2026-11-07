import base64
import functools
import http.server
import json
import os
import subprocess
import sys
import threading

import pytest

from simvltanea.lab.tests.e2e.helpers import APP, DATA, FIXTURES, ROOT


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser cancelled a media request (normal when clips swap)

    def finish(self):
        try:
            super().finish()
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture(scope="session")
def server():
    if not os.path.exists(os.path.join(FIXTURES, "data", "clips.json")):
        subprocess.run([sys.executable, "-m", "simvltanea.lab.make_fixtures"], check=True)
    handler = functools.partial(QuietHandler, directory=ROOT)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)  # port 0 = random free port
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


@pytest.fixture(scope="session")
def clips():
    with open(os.path.join(FIXTURES, "data", "clips.json"), encoding="utf-8") as f:
        return {c["id"]: c for c in json.load(f)["clips"]}


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright  # imported on use: collecting this folder needs no browser stack

    exe = os.environ["PORTVS_BROWSER_EXECUTABLE"]
    with sync_playwright() as p:
        # Same sandbox and shared-memory flags as the other browser suites (GitHub-hosted Ubuntu 24.04 runners).
        args = ["--autoplay-policy=no-user-gesture-required", "--no-sandbox", "--disable-dev-shm-usage"]
        b = p.chromium.launch(executable_path=exe, headless=True, args=args)
        yield b
        b.close()


def share_hash(values):
    """The #p=... share hash the app itself would make for a config that differs from the defaults in `values`."""
    payload = {"v": 1, "values": values, "mods": {}, "bypass": [], "locks": []}
    return "#p=" + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


class Lab:
    """Thin helper around a Playwright page running the lab."""

    def __init__(self, page, server):
        self.page, self.server = page, server
        self.errors = []
        self.requests = []
        page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.errors.append("pageerror: %s" % e))
        page.on("request", lambda r: self.requests.append(r.url))

    def open(self, query="", hash_="", data=DATA, wait=True, values=None):
        if values:
            hash_ = share_hash(values)
        q = "?data=%s%s" % (data, query)
        self.page.goto("%s%s%s%s" % (self.server, APP, q, hash_))
        if wait:
            self.ready()

    def ready(self, n=None):
        self.page.wait_for_function("window.__labReady === true", timeout=15000)
        self.page.wait_for_function("__lab.engine().length > 0 && __lab.engine().every(Boolean)", timeout=15000)
        self.settle()

    def settle(self, ms=250):
        self.page.wait_for_timeout(ms)

    def js(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def set(self, id_, value):
        assert self.js("([i, v]) => __lab.set(i, v)", [id_, value]) is True, id_

    def set_panels(self, n):
        self.set("layout.panels", n)
        self.page.wait_for_function("(n) => document.querySelectorAll('.panel').length === n && __lab.engine().every(Boolean)", arg=n, timeout=15000)
        self.settle()


@pytest.fixture
def make_lab(browser, server):
    contexts = []

    def make(viewport=(1280, 720), **ctx):
        c = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, **ctx)
        contexts.append(c)
        return Lab(c.new_page(), server)

    yield make
    for c in contexts:
        c.close()


@pytest.fixture
def lab(make_lab):
    l = make_lab()
    l.open()
    return l
