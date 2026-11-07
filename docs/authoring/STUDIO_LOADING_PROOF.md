# Studio loading proof: 7 November 2026

The repair addresses deferred decoded-frame startup and compilation blocking the interface.
The controlled benchmark uses synthetic media; physical iPhone playback and production deployment remain unverified.
The issue remains open until the release is deployed and checked.

```json
{
  "schema": "simvltanea.studio-loading-proof/1",
  "observed_at": "2026-11-07T16:04:09.870271+00:00",
  "repository": "4444J99/tool-video-loop-compositor",
  "base_commit": "a77e1defdcc246647ab715854b03498f60d83f8d",
  "live_before": {
    "url": "https://loop-compositor-studio.pages.dev/",
    "deployment": "7fec0066-ad33-4154-9716-b7fd18af3843",
    "commit": "b81c2170e2d7346a4fcfc2cb6d2fe3775bffee8b",
    "latest_git_deployment": "8dda12c5-05aa-46db-900b-14489ebb41be",
    "latest_git_deployment_result": "failed: empty build/output configuration attempted to publish archive ZIP larger than Pages 25 MiB per-file limit"
  },
  "scope": "Fix deferred-decoder startup and interface blocking while compiling Studio selections; preserve authored clock/layout/seed semantics. No repository restructuring or media publication.",
  "source_sha256": {
    "src/simvltanea/browser/browser.compiler.js": "b0d2c1c6f62a92077c586d6acc22f4478a16a82308cccc13e017bfd3336e8b93",
    "src/simvltanea/browser/browser.runtime.js": "0d090a59818a448fbb186977a201cc2aec012747de64584cf75b55a0dc140eb3",
    "src/simvltanea/browser/browser.studio.js": "1d7cd8d056cd642c8a0ca713fc0d71ff304ff3e2f8be81f651d869d7fc8e2fea",
    "src/simvltanea/browser/test_browser_studio.py": "4a09ecdcc536e209857466177e5aaba3dbcc26c73a2750d37c5c9a763411554d"
  },
  "regressions": {
    "before": "UI worker test failed and deferred-loadeddata test timed out; sound-during-initial-worker test failed before follow-up fix.",
    "after": "Five new tests passed: worker compilation, no-Worker fallback, superseded selection, first sound gesture during initial compilation, deferred decoded-frame event startup.",
    "browser_suite_before_sound_followup": "92 tests and 416 subtests passed in 221.32 seconds.",
    "full_suite": "running"
  },
  "benchmark": {
    "environment": "headless Chromium 153.0.8010.0, Linux, viewport390x844, CDP CPU throttle4, synthetic same-origin H.264/AAC library; 12 strips; three runs per condition",
    "method": "Same staged shell, layouts, synthetic media and query; only compiler/runtime/studio JS differ. PerformanceObserver longtask entries; wall time until compositionRuntime.running.",
    "runs": [
      {
        "case": "before",
        "run": 1,
        "ready_seconds": 1.438,
        "longtasks": [
          {
            "start": 508.3999999994412,
            "duration": 551
          }
        ],
        "max_block_ms": 551,
        "errors": null,
        "panels": 12
      },
      {
        "case": "before",
        "run": 2,
        "ready_seconds": 1.598,
        "longtasks": [
          {
            "start": 554.7999999998137,
            "duration": 589
          }
        ],
        "max_block_ms": 589,
        "errors": null,
        "panels": 12
      },
      {
        "case": "before",
        "run": 3,
        "ready_seconds": 1.807,
        "longtasks": [
          {
            "start": 824.7999999998137,
            "duration": 588
          }
        ],
        "max_block_ms": 588,
        "errors": null,
        "panels": 12
      },
      {
        "case": "after",
        "run": 1,
        "ready_seconds": 1.117,
        "longtasks": [
          {
            "start": 508.40000000037253,
            "duration": 122
          }
        ],
        "max_block_ms": 122,
        "errors": null,
        "panels": 12
      },
      {
        "case": "after",
        "run": 2,
        "ready_seconds": 0.992,
        "longtasks": [
          {
            "start": 408,
            "duration": 93
          }
        ],
        "max_block_ms": 93,
        "errors": null,
        "panels": 12
      },
      {
        "case": "after",
        "run": 3,
        "ready_seconds": 1.051,
        "longtasks": [
          {
            "start": 428.20000000018626,
            "duration": 94
          }
        ],
        "max_block_ms": 94,
        "errors": null,
        "panels": 12
      }
    ],
    "limits": [
      "Browser suite was also running during the benchmark; these are controlled synthetic measurements, not field Core Web Vitals.",
      "Physical iPhone/Safari, real-footage decoder capacity and universal autoplay are unverified."
    ]
  },
  "review": {
    "result": "Initial sound-during-compilation P2 fixed and regression verified. Read-only follow-up review found no residual actionable concern."
  },
  "publication": {
    "state": "pending",
    "blocker": "Cloudflare Pages asset check-missing returns HTTP403 Authorization failed, including with project-issued upload JWT. Existing live deployment has not been changed."
  },
  "lifecycle": {
    "local_branch": "fix/mobile-loading",
    "target": "main",
    "remote_main_observed": "a77e1defdcc246647ab715854b03498f60d83f8d",
    "retirements": [],
    "preservation": "Original commits retained in origin/main; isolated worktree retains implementation and generated tests.",
    "status": "partial"
  }
}
```
