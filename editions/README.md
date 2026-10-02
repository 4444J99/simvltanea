# Production editions

`registry.json` is the authoritative `triptych.editions.v1` registry.
Source and project locations use logical references such as `@samples/inaugural`
and `@examples/project.example.json`. Loaders resolve these through the selected
workspace layout.
Safe templates remain in `examples/`; generated output belongs under `var/`.

```bash
python3 -m tools.verification.verify_editions
python3 -m tools.editions.edition_status
```

See [edition authoring](../docs/authoring/EDITION_AUTHORING.md).
