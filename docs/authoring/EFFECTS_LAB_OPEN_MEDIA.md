# Optional public media sources

The editing workspace opens empty. Its optional Public media picker supplies
recorded footage and found sound, selected in response to the user's correction
that generated music and supplied illustrations are unsuitable material.

The catalog is fixed. It accepts no arbitrary media URLs from imported project
files. Choosing a source downloads it to a browser-owned File/Blob and admits it
through the same native-media path as a local import. User media is not uploaded.
Saved projects retain a catalog ID, settings, and stable clip identity; they do
not embed media bytes, blob URLs, or arbitrary network URLs.

## Creators and reuse records

| Catalog source | Creator | Source and rights record | Rights |
| --- | --- | --- | --- |
| Rainy night in Sham Shui Po | Andy Li | [Original video page](https://commons.wikimedia.org/wiki/File:Rainy_night_in_Sham_Shui_Po.webm) | CC0 1.0 |
| Stream of flowing water | Patjos.scot | [Original video page](https://commons.wikimedia.org/wiki/File:StreamOfFlowingWater.webm) | CC0 1.0 |
| Flowing water | Fg2 | [Original recording and declaration](https://commons.wikimedia.org/wiki/File:Flowing-water-100019.ogg#Licensing) | Author's worldwide public-domain release |
| Compressor motor | stephan | [Original recording and declaration](https://commons.wikimedia.org/wiki/File:Compressor_motor.ogg#Licensing) | Author's worldwide public-domain release |

The two videos use the [CC0 dedication](https://creativecommons.org/publicdomain/zero/1.0/).
The two audio recordings carry explicit author public-domain releases; they are
not labelled as CC0 works. The creator and rights links remain available in the
picker even where credit is not required by the stated rights record.

## Verified delivery variants

These exact links were extracted from each Commons page's media-source elements
and verified on 2026-11-08 UTC. They are existing Wikimedia transcodes. The app
does not reencode them or substitute a musical soundtrack.

| Source | Delivered format | Bytes | Duration observed in Chromium |
| --- | --- | ---: | ---: |
| [Rainy night](https://upload.wikimedia.org/wikipedia/commons/transcoded/3/36/Rainy_night_in_Sham_Shui_Po.webm/Rainy_night_in_Sham_Shui_Po.webm.480p.vp9.webm) | VP9 / Opus WebM, 270 × 480 | 201,419 | 6.121 s |
| [Flowing stream](https://upload.wikimedia.org/wikipedia/commons/transcoded/e/e0/StreamOfFlowingWater.webm/StreamOfFlowingWater.webm.480p.vp9.webm) | VP9 / Opus WebM, 640 × 480 | 7,646,133 | 55.756 s |
| [Flowing-water recording](https://upload.wikimedia.org/wikipedia/commons/transcoded/2/26/Flowing-water-100019.ogg/Flowing-water-100019.ogg.mp3) | MP3, 44.1 kHz stereo | 489,308 | 18.899592 s |
| [Compressor recording](https://upload.wikimedia.org/wikipedia/commons/transcoded/d/db/Compressor_motor.ogg/Compressor_motor.ogg.mp3) | MP3, 44.1 kHz stereo | 60,364 | 3.879184 s |

Each returned HTTP 200, `Access-Control-Allow-Origin: *`, and
`Accept-Ranges: bytes`. These are observations at the verification time, not
guarantees of future external availability. The app reports download or decode
failure rather than claiming a clip was admitted.

The pages' 360p MOV alternatives were inspected and contain MPEG-4 Part 2 video
with MP3 audio, not H.264; they are not the catalog's selected variants.

## Playback verification and limits

Chromium 157.0.8103.38 loaded all four exact downloaded assets through the actual
workspace engine using Blob URLs. Native sound playback advanced and its sampled
signal was nonzero for each source. Both videos decoded visible frames and their
separate picture and sound clocks advanced. Extracted frames showed the recorded
urban night scene and flowing stream.

This establishes a working decoder and signal path for that browser. It does not
establish physical iPhone acceptance, seamless loop boundaries, or artistic
acceptance by the user. The recordings are supplied as source material to edit.

See the [workspace guide](EFFECTS_LAB.md) for direct editing and the distinction
between looping region duration and source-frame in/out trimming.
