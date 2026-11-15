# AgentPets asset conversion

`convert_agentmascot.py` reads statically extracted JSON data. It never executes
the source archive's runtime. Install the repository's locked frontend
dependencies through the normal authorized setup before using the converter;
Node.js and `plugins.v3/agentpets/frontend/node_modules/prettier` must exist.
The converter does not install tools or access the network.

```text
python scripts/agentpets/convert_agentmascot.py extracted-data.json output/packs --archive-sha256 <sha256>
```

Use a new output directory. Existing pack directories are not overwritten.
Both `pack.json` and `provenance.json` use the frontend Prettier configuration
and UTF-8 without BOM with LF endings, including on Windows. Check the generated
JSON, image hashes and source archive hash before replacing committed assets.

## Lossless UI avatars

The six editable PNG avatars remain the source originals and keep their published
static paths. The frontend imports separate `avatar.ui.webp` derivatives as
inline data URLs; the build does not emit these extra UI files as static assets.

`optimize_ui_avatars.py` validates the existing derivatives by default:

```text
python scripts/agentpets/optimize_ui_avatars.py
```

Use the workspace's verified test Python on Windows. Pillow with WebP support is
required. Generation checks dimensions, every RGBA pixel, ICC profiles and EXIF,
then checks the total byte reduction. The committed files were generated with
Pillow 12.3.0 using lossless WebP, exact transparent pixels and method 6.

`--write` creates only missing derivatives and refuses existing outputs. For
regeneration, prepare the PNG paths in a fresh directory in the active task's
archive batch, pass `--assets-root <directory> --write`, verify the result, then
apply the reviewed derivatives to the authorized checkout. Keep the PNG originals
unchanged unless the task explicitly changes the artwork.
