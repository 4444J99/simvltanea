"""Shared constants and geometry checks for the lab's Playwright suite.

The suite serves the repository root on 127.0.0.1 (a random port), so the app and the synthetic
fixtures below var/ are same-origin, exactly as the manual run in docs/authoring/LAB.md.
"""
from simvltanea.lab import APP_DIR, FIXTURES_DIR
from simvltanea.paths import REPO_ROOT

ROOT = str(REPO_ROOT)                                            # served directory
APP = "/" + APP_DIR.relative_to(REPO_ROOT).as_posix() + "/"      # /src/simvltanea/lab/app/
DATA = "/" + FIXTURES_DIR.relative_to(REPO_ROOT).as_posix() + "/"  # /var/proofs/lab-fixtures/
FIXTURES = str(FIXTURES_DIR)

GEOMETRY_JS = """() => {
  const r = (e) => { const b = e.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height}; };
  return {
    W: innerWidth, H: innerHeight, axis: __lab.axis(), overlap: __lab.effective()['layout.overlap'],
    panels: [...document.querySelectorAll('.panel')].map((p) => ({
      rect: r(p), compact: p.classList.contains('compact'),
      videos: [...p.querySelectorAll('video.on')].filter((v) => v.getAttribute('src')).map(r),
    })),
  };
}"""

EPS = 0.51


def check_tiling(geo, overlap_exact=None):
    """Assert the panels tile the viewport (except configured overlap) and every video covers its cell."""
    W, H, axis, ov = geo["W"], geo["H"], geo["axis"], geo["overlap"]
    ps = sorted(geo["panels"], key=lambda p: p["rect"]["x"] if axis == "columns" else p["rect"]["y"])
    a, s, total = ("x", "w", W) if axis == "columns" else ("y", "h", H)
    cross, crosssize, ctotal = ("y", "h", H) if axis == "columns" else ("x", "w", W)
    assert ps, "no panels"
    assert abs(ps[0]["rect"][a]) < EPS, "first strip does not start at the edge"
    assert abs(ps[-1]["rect"][a] + ps[-1]["rect"][s] - total) < EPS, "last strip does not reach the far edge"
    for i, p in enumerate(ps):
        r = p["rect"]
        assert abs(r[cross]) < EPS and abs(r[crosssize] - ctotal) < EPS, "strip %d does not span the full cross axis: %s" % (i, r)
        assert r[s] >= 1
        if i:
            prev = ps[i - 1]["rect"]
            gap = r[a] - (prev[a] + prev[s])
            assert gap <= EPS, "gap of %.2fpx before strip %d" % (gap, i)
            overlap = -gap
            expect = ov if overlap_exact is None else overlap_exact
            assert abs(overlap - expect) <= 1.01 or ps[i]["rect"][s] < 2 * expect + 2, "overlap %.2f != %s" % (overlap, expect)
        assert p["videos"], "strip %d has no visible video" % i
        for v in p["videos"]:
            assert v["x"] <= r["x"] + EPS and v["y"] <= r["y"] + EPS, "video does not cover cell start (strip %d): %s vs %s" % (i, v, r)
            assert v["x"] + v["w"] >= r["x"] + r["w"] - EPS and v["y"] + v["h"] >= r["y"] + r["h"] - EPS, "video does not cover cell end (strip %d)" % i
