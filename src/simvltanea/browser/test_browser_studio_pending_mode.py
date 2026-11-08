"""A loop-mode change must preserve the share link for a pending panel edit."""
from __future__ import annotations

import unittest

from simvltanea.browser import test_browser_studio_settlement as fixture


PENDING_MODE_COMPILERS = r'''(() => {
  const ObservedWorker = Worker;
  window.pendingModeCompilers = [];
  window.Worker = class extends ObservedWorker {
    postMessage(...args) {
      if (!window.holdModeCompilers) return super.postMessage(...args);
      settlementCompilers.add(this);
      pendingModeCompilers.push(() => {
        if (!this.settlementTerminated) super.postMessage(...args);
      });
    }
  };
  window.releaseModeCompilers = () => {
    window.holdModeCompilers = false;
    pendingModeCompilers.splice(0).forEach(send => send());
  };
})();'''


class StudioPendingModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.StudioSettlementTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.StudioSettlementTests.tearDownClass.__func__(cls)

    open = fixture.StudioSettlementTests.open
    snapshot = fixture.StudioSettlementTests.snapshot
    playing = fixture.StudioSettlementTests.playing
    unlock = fixture.StudioSettlementTests.unlock
    tap = fixture.StudioSettlementTests.tap
    ready = fixture.StudioSettlementTests.ready
    settled = fixture.StudioSettlementTests.settled
    tap_panel = fixture.StudioSettlementTests.tap_panel
    report = fixture.StudioSettlementTests.report
    assert_plan_matches_residents = fixture.StudioSettlementTests.assert_plan_matches_residents

    def test_mode_change_keeps_pending_panel_edit_in_published_mix(self):
        # One resident makes the tapped replacement genuinely new, so resident
        # normalization cannot incidentally repair a lost share-link request.
        page = self.ready(count=1, site='settlement-variant', init_script=PENDING_MODE_COMPILERS)
        page.evaluate('window.holdModeCompilers = true')
        self.tap_panel(page, 'loop-1')
        page.wait_for_function('() => pendingModeCompilers.length === 1')
        requested = self.snapshot(page)
        self.assertNotEqual(requested['selection'], [self.ids[0]])
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => pendingModeCompilers.length === 2')
        page.evaluate('releaseModeCompilers()')
        self.settled(page)
        result = self.report(page, 'pending-panel-mode-share')
        self.assertEqual(result['snapshot']['selection'], requested['selection'])
        self.assertEqual(result['snapshot']['loopMode'], 'forward')
        self.assert_plan_matches_residents(result)
        self.assertEqual(page.evaluate('new URLSearchParams(location.search).get("seed")'), str(requested['seed']))
        self.assertEqual(result['mix'], 's' + str(self.ids.index(requested['selection'][0])))
