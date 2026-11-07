# Effects Lab

Effects Lab is an instrument for trying relationships between layers while they
play. It opens from the **Effects Lab** link in Studio, or directly at `lab.html`
in a staged compositor site. Its controls affect this live session; authored
composition rendering and export retain their existing behavior.

The earlier [dataset Lab](LAB.md) explores strip layout, framing, pool selection,
and source metadata. Effects Lab adds a focused surface for visual layer
blending and independent audio/video voices. Its implementation shares the
Studio's master audio protection and static publication path.

## Start playing

Press **Play session** to unlock sound and start the first layer. The three
starter sources are procedural pictures and synthesized loops, generated on the
device. They demonstrate the controls without needing to download media.

Select a layer to change its picture, sound, or motion. Launch another layer to
hear and see the overlap immediately, or leave automatic succession on. A clip
launches its sound and picture together. After launch, their media positions,
repeat counters, rate decisions, and lifetimes are independent.

Use a video or audio file from the device to try the effects on real material.
Files are read through local object URLs and are never uploaded. At most four
clip pairs are admitted. A failed import leaves the existing composition in
place. Browser codec support determines which media can be played.

## Picture layers

The stage blends pictures in layer order. The bottom visible picture is drawn
normally onto the dark background; each higher picture blends with the result
below it. Move a layer forward or backward to change the interaction.

Available modes are Normal, Screen, Multiply, Overlay, Soft light, Difference,
Exclusion, Color dodge, Lighten, and Darken. Opacity and the picture's presence
envelope determine how much it contributes. Brightness, contrast, saturation,
hue, blur, and inversion are separate controls for the selected layer.

## Sound and presence

Each layer has its own comb effect and spectral pass stages. The comb spacing
sweeps logarithmically between its low and high settings, then returns. Sweep
period is one complete round trip, and voices use different phase offsets.
The sound inspector shows the current spacing rather than a low-pass cutoff:
a comb acts on multiple repeated bands across the spectrum.

The comb uses finite feed-forward delay taps with controlled decay. Its
resonance control changes those tap weights. There is no infinite feedback
loop: this keeps the upper end of the sweep accurate without depending on an
audio worklet or the minimum feedback-cycle delay in the
[Web Audio rendering rules](https://www.w3.org/TR/webaudio/). The saved-settings
key `combFeedback` names this decay parameter for the first lab format.

Presence mode opens a low-pass filter on entrance and uses high-pass filtering
as the sound recedes. Reverse presence exchanges those roles. Manual low-pass,
high-pass, band-pass, and bypass choices allow direct comparison. The pass
filter and comb amount can be controlled independently.

The existing compositor master graph supplies compression and sample limiting.
It does not claim true-peak limiting. Start with the provided moderate master
level and adjust the selected voice's level as needed.

## Independent repeats and departures

Picture rate and sound rate each have a base value and a separate amount of
variation per repeat. A loop's next rate is chosen only when that loop repeats;
an audio repeat does not change the picture's speed, and vice versa. Rates are
bounded to 0.25–3 times normal speed.

The default is varispeed sound: changing the audio rate also changes its pitch.
Pitch preservation is available where the browser supports it for the selected
source. The interface must not imply that a visual loop clock controls sound.

Both lifetimes use a rise to a peak followed by a longer fall. Picture lifetime
and sound lifetime can differ. A picture may finish while its sound remains
active. Automatic succession waits for an inactive pair before reusing it, so
it does not cut off a surviving sound merely to reuse its picture.

Manual launch deliberately restarts the selected pair. Global pause freezes
the session, and resume retains both positions. Holding a layer keeps it present
after its entrance. Turning off only its picture provides a quick way to hear
the independent audio.

## Settings

Presets provide starting points, not artist-approved decisions. Settings can be
saved locally and exported/imported as JSON. Media bytes and object URLs are not
part of a settings file; imported local media must be selected again after a
reload. Unresolved local files remain visible in their saved stack positions;
their settings survive another save or export before reselection. Choosing the
matching file restores that position. Saved settings do not synchronize between
devices.

## Build and acceptance

```bash
PYTHONPATH=src python -m simvltanea.browser.browser_studio --output var/site/studio
```

Open the staged `lab.html` using the supported local or hosted preview. The lab
adds five declared assets to the existing five-file Studio output; public
library staging uses that same file list and still rejects unrelated files.

Desktop and emulated phone checks are separate evidence from physical iPhone
Safari. This feature does not close the ongoing native Studio WebKit continuity
investigation. See [Studio playback](STUDIO_PLAYBACK.md) for that boundary.
