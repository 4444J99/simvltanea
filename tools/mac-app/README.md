# Simvltanea for Mac

A native macOS app that plays the Studio over your own Photos videos. The Studio is the same
one the web site ships; the app adds a private clip library built from Photos with PhotoKit.

## What is here

| Part | Path | Job |
| --- | --- | --- |
| Kit | `sources/kit` | Library format, audio analysis, local server, Photos import planning |
| App | `sources/app` | SwiftUI window around a web view, plus the Photos import button |
| Tool | `sources/tool` | `simv-library`: import a folder, verify a library, serve a Studio without the app |
| Tests | `tests/kit` | `simv-tests`, an assertion runner (the Command Line Tools ship no XCTest) |

## How it works

1. **Import.** PhotoKit lists your videos. `ExportPlanner` keeps those between 1 and 30 seconds
   that were not imported or refused before, favourites first and then newest first. Each is
   exported to MP4 (at most 64 MiB and 4096 px, with smaller presets as fallbacks) and
   probed for size and duration.
2. **Sound.** Each clip's audio is decoded once and measured: peak, BS.1770-4 integrated
   loudness with the R128 gates, and a 10 Hz RMS envelope. Silent clips record explicit nulls.
3. **Library.** Files are named by the first 12 hex digits of their SHA-256 and listed in
   `library/manifest.json` (`simvltanea.public-demo/1`), written atomically.
   `tests/test_macos_app.py` proves the Python stager accepts this library unchanged.
4. **Play.** A loopback-only HTTP server (with range support) serves the staged Studio and
   the library to the web view. `127.0.0.1` is a secure context, so the Studio's
   `crypto.subtle` clip check works, and WebKit gets the range requests video needs.

Originals in Photos are never modified. The library lives in
`~/Library/Application Support/Simvltanea`. Nothing is uploaded.

## Build and run

```bash
tools/mac-app/build_app.sh            # writes var/site/mac-app/Simvltanea.app, ad-hoc signed
open var/site/mac-app/Simvltanea.app

cd tools/mac-app
swift build --build-system native
swift run --build-system native simv-tests          # the Swift suite
.build/debug/simv-library import-folder <videos> <root>
.build/debug/simv-library verify <root>
.build/debug/simv-library serve <studio-dir> <root>
```

`--build-system native` is needed on this toolchain; the default build system fails to start.

## Not done yet

- Playback was checked in Chromium, not in WebKit. A hidden Browser pane showed one of four
  decks playing and "That loop could not start" on the rest; the cause was the pane giving the
  page about 3 animation frames a second, which starved the Studio's two-fresh-frames check
  (fixed in `browser.live.js`; the same site played all four decks in unthrottled headless
  Chromium, and in the pane after the fix). Whether all four decks play in the app's WKWebView
  is unobserved.
- The app was built and its library and server were exercised, but the Photos permission
  prompt and the web view playing a real Photos import have not been observed in a running
  app window.
- No in-app choice of album, date range or clip count; the import button takes the defaults
  and a favourites switch.
- Variants (boomerang seams) and per-clip tags are not produced natively; clips play forward.
- No Developer ID signing or notarisation.
