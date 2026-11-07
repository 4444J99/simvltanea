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
- [ ] Exercise actual browser rendering and Web Audio, including single-voice
  swelling, overlapping successors, disabled filters, pause, reduced motion,
  corrupt replacement, and cleanup. Run repository verification gates.
- [ ] Review the complete diff independently, publish a feature branch and
  reviewable PR, and verify the published revision. Record delivery status.

## Review focus

1. Normalization must not cancel a single clip's amplitude envelope.
2. A successor must not inherit its predecessor's closing filter or lifetime.
3. Delayed or failed replacement must preserve the outgoing decoder and picture.
4. Mute, pause, reduced motion, and bypass must remain authoritative.
5. Reusing a deck must not retain stale filter automation or multiply audio nodes.

## Verification boundary

Browser tests establish behavior in the named test browser. Linux WebKit is not
physical iPhone Safari acceptance. This change does not itself resolve issue #85
or establish production deployment. Historical context and older approvals do
not authorize a new merge, deployment, or repository restructuring.
