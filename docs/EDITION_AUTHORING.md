# Edition authoring and production

The production registry is `editions.json`. Project settings are supplied by
`examples/project.example.json`. Generated projects, media, renders, sites,
and packages live below `var/`.

## Inaugural engineering edition

Run from the repository root:

```bash
python3 -m tools.media.make_inaugural_fixture
python3 -m tools.editions.build_edition simvltanea-inaugural
python3 -m tools.verification.verify_editions
python3 -m tools.editions.edition_status
```

The builder stages clips in `var/samples/editions/<slug>/` and writes a project
under `var/work/editions/<slug>/`. Use `--dry-run` to inspect the commands.

## Personal media

```bash
python3 -m tools.media.import_folder /path/to/clips \
  --project var/work/project.folder-local.json \
  --output-dir var/samples/folder-import --mode symlink
```

Apple Photos importers are in `tools.media.import_photos` and
`tools.media.import_photos_visuals`; inspect `--help` before selecting a
library or album. Media atomization inventories and hashes existing clips:

```bash
python3 -m tools.media.atomize_media --lanes samples --no-ffprobe
```

It does not transcode or normalize video.

## Rendering and distribution

The historical project exporter handles three-panel projects. For compiled
N-loop states, use the versioned renderer:

```bash
PYTHONPATH=src python3 -m simvltanea.render_triptych \
  --state var/proofs/state-3.json --orientation portrait \
  --output var/renders/edition-portrait.mp4
```

Static distribution commands are `tools.publishing.build_site_index`,
`tools.verification.verify_public_site`, and
`tools.publishing.package_public_site`. Their defaults are `var/site/` and
`var/packages/`. See [the structure contract](STRUCTURE.md) and
[audio architecture](AUDIO_ARCHITECTURE.md) for further details.
