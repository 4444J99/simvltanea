# Clip presence filters implementation plan

## Intent and design

Implement the owner's requested rise, peak, and fall of a clip's audible and
visible presence as subsequent clips supersede it. Build on the persistent
Studio session and finite resident lifetimes introduced by PR #88, based on
`63612a9a7394d8b4e1ec1d375baaa17eaf265eb9`. This is a Studio feature; authored
composition schemas and exports keep their existing behavior.

One presence envelope drives audio gain, a low-pass filter, image brightness,
saturation, and restrained blur. The engineering defaults are a 1.2-second
linear rise followed by a longer linear fall over the resident's planned life.
A 0.12 tail holds until a decoded successor is ready; the existing two-deck
handoff then completes departure. These tuning values are implementation
choices, not a claim of artistic approval.

Apply gain modulation after ecological normalization so a solo voice can swell
and recede. Each arriving deck owns its entrance time and filter state. Keep the
outgoing image opaque underneath the incoming alpha during source-over blends;
fading both image alphas would expose the black background. Filters use brightness
0.55–1, saturation 0.3–1, blur 2–0 CSS pixels, and a logarithmic low-pass opening
from 420 Hz to at most 16 kHz or 45% of the audio sample rate.

An accessible Filters button enables comparison with unfiltered playback and
persists the explicit choice in `fx=0` / `fx=1`. Reduced-motion mode bypasses
animated filtering. Holding automatic changes keeps current residents at steady
presence after their entrance; a held clip must not fade away indefinitely.

### Approaches considered

| Approach | Consequence |
| --- | --- |
| Only animate master volume and the whole stage | All clips breathe together and individual supersession is lost |
| Add effects to the compiled authored timeline | Broadens schema/export scope and misses the live resident lifecycle |
| Drive per-deck effects from the existing live lifecycle | Preserves independent clocks, bounded preparation, and moving overlap; selected |

## Implementation

- [x] Add a pure `browser.presence.js` envelope/filter target module and behavioral
  tests, with scheduler presence output separate from normalized mix gains.
- [x] Integrate independent per-deck presence into `browser.live.js`, preserving
  gain safety, first-gesture audio, rollback, pause, and decoder limits.
- [x] Bundle the helper and connect scheduler output in Studio. Add the Filters
  control and URL state without replacing videos or audio nodes.
- [x] Exercise actual browser rendering and Web Audio, including single-voice
  swelling, overlapping successors, disabled filters, pause, reduced motion,
  corrupt replacement, and cleanup. Run repository verification gates.
- [x] Review the complete diff independently and prepare the feature branch
  for a reviewable PR with verification commands and delivery boundaries.

## Review focus

1. Normalization must not cancel a single clip's amplitude envelope.
2. A successor must not inherit its predecessor's closing filter or lifetime.
3. Delayed or failed replacement must preserve the outgoing decoder and picture.
4. Mute, pause, reduced motion, and bypass must remain authoritative.
5. Reusing a deck must not retain stale filter automation or multiply audio nodes.

## Verification record

On 2026-11-07 the complete presence, ecosystem, live-session, and Studio suites
passed: **102 tests and 377 subtests**, with no skipped feature tests. The run used
Chrome for Testing Headless Shell 157.0.8103.38, Playwright 1.57.0, and FFmpeg 6.1.1.
It exercised native H.264 playback, measured Web Audio output, rendered pixels,
overlapping successors, rejected promotion, pause, reduced motion, bypass, and
the canvas fallback's disabled control. Independent review found no outstanding
Critical or Important code issues.

Repository structure, feature boundaries, layout synchronization, plan indexing,
lifecycle, editions, naming, Markdown, and JavaScript syntax checks passed.
The broader repository run reported a Lab end-to-end wrapper failure and later
stopped reporting progress; it was interrupted. **That attempt is not a passing
full-suite result.** Lab application and test files are unchanged from the base
revision. The PR records the broader validation findings and published revision.

Delivery uses `feat/clip-presence-filters` and a draft PR against `main`.

## Verification boundary

Browser tests establish behavior in the named test browser. Linux WebKit is not
physical iPhone Safari acceptance. This change does not itself resolve issue #85
or establish production deployment. Historical context and older approvals do
not authorize a new merge, deployment, or repository restructuring.
