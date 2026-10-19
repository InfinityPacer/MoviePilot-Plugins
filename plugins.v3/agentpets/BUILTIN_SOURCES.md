# Built-in frame mascots

These three local built-ins were adapted from the user-provided archive
`agentmascot_v0.1.18-behavior-actions-slim.zip`.

- Archive SHA-256: `019cbc33013486db096d31547738cf948bdeaad7798734977b79cdcdb2c11686`.
- Source plugin author: `ifsherlock`.
- Source repository recorded in the archive: `https://github.com/ifsherlock/MoviePilot-Plugins`.
- Source profiles: `chibiterasu`, `nailong`, and `kurisu`.
- The archive filename says 0.1.18, but its Python metadata says 0.1.15 and its
  package metadata says 0.1.16. The archive hash, not those inconsistent version
  labels, identifies the exact source used here.

The source describes Chibiterasu as original Shimeji action poses and Nailong as
AI-generated animation frames. It describes Kurisu as a chibi researcher frame
set. No separate artwork license was included in the supplied archive. This
local integration does not assert a new artwork license or authorize a public
redistribution; confirm source artwork terms before a public release.

## Conversion

`scripts/agentpets/extract_agentmascot.mjs` parses constant data with the
TypeScript AST. It does not execute the source runtime. The Python converter
creates lossless WebP atlases, retains the original image references and
action ordering, and records source-image hashes in each `provenance.json`.
Per-pose anchors are normalized relative to the action surface; rightward
walking uses mirrored source cells. No browser injection, entry replacement,
mouse-following engine, wall climbing, ceiling physics, or other source runtime
code is bundled.

The original timing unit is 33 ms. Individual frame durations are retained;
holds longer than 5 seconds use repeated identical cells. A 33 ms ceiling pose
is extended to the existing player's 40 ms minimum. Wall and ceiling artwork
remains available in the animation preview without enabling those movements.

The derived peek action for Nailong and Kurisu holds the native idle frame for
3200 ms, then uses the existing closed-eye frame for 140 ms. Both frames share
one fixed baseline and the original open-eye landmarks. Chibiterasu has no separate idle blink
and retains its original pose. No source images or native action timings change.

The stable IDs are `builtin-chibiterasu`, `builtin-nailong`, and `builtin-kurisu`.
They are read-only built-in packs and do not occupy or rewrite the user's pack
store. Each supports AgentPets' per-pet size and speed settings. Display
calibration and action mappings are supplied by the built-in pack, not edited
in the user-pack store.

## Z256 Kurisu

`builtin-kurisu-z256` is a separate built-in copied from the user's installed
`kurisu-v2` Pet, named `克里斯蒂娜` with the description `z256专属`.
The original imported item is retained, and its ID is not reserved or shadowed.

The original 1536 x 2288 PNG is stored without re-encoding as `sheet.png`.
Its SHA-256 is
`b09ee371efb0b51cdb5a88346389f01d29251c692a5448fe463b1b258ba67af7`.
The frontend renders a lossless `sheet.webp` copy with an exact decoded RGBA
pixel match. This follows the existing WebP asset delivery path because PNG
static requests return nginx 404 on the validated instance. The PNG remains
unchanged in the pack; no proxy settings are changed.
The original actions, mappings, calibrated crop, eyes and head position are
retained; the frontend applies the same Codex v2 stage adapter used for imported
Pets. Avatar and preview PNGs are the existing cached images, not new artwork.
An additional peek action uses the existing `idle` and `blink` cells with a
3200 ms open-eye hold and a 140 ms blink; the ten original actions are unchanged.

This documents user-requested local integration. It does not assert an
additional public artwork license; distribution terms remain a PR readiness
check separate from local installation.
