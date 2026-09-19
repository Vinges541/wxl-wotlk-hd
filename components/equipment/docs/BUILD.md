# Build and review

Use explicit paths to a private workspace outside the client. Do not put generated
assets or weights into source control. All paths below are examples.

## Selected direct ×2 recipe

The recommended recipe is `direct-smooth`, available in both `wxl_equipment.batch`
and `wxl_equipment.npc` processing commands. It is the default for these two commands;
pass `--recipe conservative` to reproduce the older bounded-detail experiments.
The single-item `wxl-equipment infer` command remains the conservative comparison.

Create the inventories described below, then run:

```sh
HF_HUB_OFFLINE=1 python -m wxl_equipment.batch process \
  --workspace /private/work/full --weights /private/work/realesrnet/model.safetensors \
  --lock models/realesrnet.json --recipe direct-smooth
```

This recipe uses 2× dimensions for **all** Item textures. The inventory's original
storage estimate describes the conservative profile; direct body layers require
four times its pixel storage. Full-frame inputs must not exceed 1024 per dimension
or 1,048,576 pixels, and outputs must fit 2048. `--strength` is ignored for direct RGB.
A changed recipe creates a separate cache identity, never reuses conservative pixels.

Cache files intentionally retain nearest-replicated alpha. Run the cache auditor,
then `pack`: it converts all mips to the runtime encoding before smoothing only
alpha. Review the **packaged** BLPs over contrasting backgrounds too; cache audit
sheets do not display that final contour treatment. Body RGB remains palettized;
objects and NPCs remain ARGB8888. Do not copy a lossless cache BLP into the client.

The existing installers require preview, a closed game and guarded checkpoints.
They do not replace a different Item patch automatically or know another user's
checkpoint paths. Coordinate installation on your own client. Retain original NPC
inputs: inventorying an already-upscaled overlay again would upscale it a second time.

## 1. Source extraction

Build StormLib 9.30 from wxl-core revision
`3990e09b5f80e77351d605dcd48d76b68ab2c2bf`, `deps/stormlib`:

```sh
cmake -S /path/to/wxl-core/deps/stormlib -B /private/work/storm -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build /private/work/storm
```

On macOS CMake may produce `storm.framework/storm`, not `libstorm.dylib`.
Supply build-12340 Item.dbc (8 fields) and ItemDisplayInfo.dbc (25 fields).
Prefer DBCs read from the locale MPQs; server files must be compared first. For example, extract the locale table without changing any archive:

```sh
wxl-equipment read-asset --stormlib /private/work/storm/storm.framework/storm \
  --archive /path/to/client/Data/ruRU/patch-ruRU-3.MPQ \
  --name DBFilesClient/Item.dbc --output /private/work/Item.dbc
```

Repeat for `ItemDisplayInfo.dbc`; supply additional archives in priority order
when a file is not present in the first archive. Custom input archives remain possible, so the inventory records hashes.

```sh
wxl-equipment extract --stormlib /private/work/storm/storm.framework/storm \
  --archive /path/to/client/Data/patch-3.MPQ \
  --archive /path/to/client/Data/patch-2.MPQ \
  --archive /path/to/client/Data/patch.MPQ \
  --archive /path/to/client/Data/lichking.MPQ \
  --archive /path/to/client/Data/expansion.MPQ \
  --archive /path/to/client/Data/common-2.MPQ \
  --archive /path/to/client/Data/common.MPQ \
  --items /private/work/Item.dbc --displays /private/work/ItemDisplayInfo.dbc \
  --item 38 --item 6098 --item 16864 --item 16865 --item 25 --item 19364 \
  --output /private/work/slice
```

Archive arguments are highest priority first. Exclude installed overlays from source
inputs. The extractor retains male/female/unisex variants, source archive names,
hashes, sizes, alpha, mip counts and associated object models.

## 2. Optional historical Retail comparison

The selected bulk workflow skips this entire section. It uses only the supplied
legacy MPQs; no Retail downloads, material imports or model substitutions are needed.

Evaluate free space and download requirements first. The pilot uses wow.export
0.2.19, Retail 12.1.0.69587 / BuildConfig
`c9fa1a64b0170829cc5c5c98c71025c3`. Other builds require a separate profile.

`tools/prepare_exporter.py --app /path/to/wow.export.app --cache /path/to/casc
--output /private/work/exporter` copies the exporter and cache, verifies cached
SHA-1 integrity entries and remaps their absolute keys. It never edits the input
application. Copying a cache without rekeying can cause large redownloads.
The adapter is an internal-interface integration, not an upstream plugin API.

Launch the copied app with `--user-data-dir=/private/work/exporter/profile` and:

- `WXL_EQUIPMENT_EXPORT=/private/work/retail`
- `WXL_EQUIPMENT_BUILD=c9fa1a64b0170829cc5c5c98c71025c3`

It writes seven item/material/model tables and build metadata, then exits.

```sh
python tools/plan_retail.py --retail /private/work/retail \
  --inventory /private/work/slice/inventory.json \
  --build c9fa1a64b0170829cc5c5c98c71025c3
```

Relaunch with `WXL_EQUIPMENT_FILES=1` to fetch the explicit request list (maximum
32 files per pilot). Then compare:

```sh
python -m wxl_equipment.retail --workspace /private/work/slice --retail /private/work/retail
```

The join retains modifier-0 appearance, component section, material usage and model
bindings. Additional appearance modifiers need explicit investigation. Identical
pixels are not an upgrade. Different pixels are unresolved, not automatically
accepted. No Retail import was justified for the tested pilot.

## 3. Local inference

Model source URLs, sizes, revisions and hashes are in `models/*.json`.
MLX x4plus/general locks refer to already-converted safetensors. RealESRNet refers
to the official `.pth` and its deterministic local FP32 conversion:

```sh
# Run the first stage in an optional PyTorch environment (.[parity]).
python tools/convert_weights.py numpy --input /private/work/RealESRNet_x4plus.pth \
  --output /private/work/weights.npz --sha256 a820b9bde89a874d7599d545567308ce6c128fc8754a53208eda016d40aa81df
# Run the second stage in the MLX environment.
python tools/convert_weights.py mlx --input /private/work/weights.npz \
  --output /private/work/realesrnet/model.safetensors \
  --sha256 b6f5752e7998b56faa3a9aa1e0c368be8fa96d04aa6838f4e20a36abfeca1d22

HF_HUB_OFFLINE=1 wxl-equipment infer --workspace /private/work/slice \
  --weights /private/work/realesrnet/model.safetensors --lock models/realesrnet.json \
  --device mlx-gpu --scale 2 --strength 0.35
```

The runtime requires real Metal access. A sandbox hiding the GPU can fail even on
supported hardware; failure must not be described as CPU-backed Metal success.
There is no implicit CPU fallback and no weight download inside this command.

The conservative batch uses scale 1 for body layers. The separate quality pilot
below compares native-size restoration with 2× layers for the client's supported
512-square composition path. Object
textures use the requested scale. Full-frame limits are 1024 pixels per dimension
and 1048576 input pixels, with packaged dimensions capped at 2048. Large RealESRNet
inputs evaluate intermediate residual-dense blocks and upsampling stages eagerly,
preserving the complete image receptive field and FP32 weights. Spatial tiling is
rejected; no halo approximation is used.
The pipeline keeps original alpha exactly (nearest integer replication when enlarged),
retains baseline low frequencies and bounds neural RGB detail correction to
`24 * strength` per channel. No guarantee of invented-detail correctness is implied.

Each source/model/settings/implementation/runtime tuple has its own cache key.
Results include raw neural PNGs, filtered PNGs, BLPs, controls, hashes and timings.
Save `inference.json` as `general-inference.json`, `x4plus-inference.json` or
`realesrnet-inference.json` after each comparison run; `tools/compare_models.py`
creates comparison sheets and non-ground-truth fidelity diagnostics.

## 4. Prepare and preview

Review complete item texture sets, both sex variants, masks and all material passes.
Pass accepted cache keys explicitly:

```sh
python -m wxl_equipment.package prepare --workspace /private/work/slice \
  --output /private/work/package --accept REVIEWED_CACHE_KEY
python -m wxl_equipment.package install --client /path/to/client --package /private/work/package
```

Package name: `Patch-WXL-Equipment.MPQ`, a loose directory supported by the existing
WarcraftXL named-patch runtime. The installer rejects overlapping loose patches and
unknown archive overlays; it does not guess archive ordering. Existing different
equipment packages must first be rolled back. The pilot has no collisions with the
modern-race patch, so ordering between these two overlays cannot change its assets.

## 5. Install / rollback

Close WoW, verify the supported patched executable/runtime, retain the established
Wine/x87sidecar launcher and settings. Add `--apply` to the reviewed installation
command. The installer does not configure or launch the game. It checks processes,
paths and hashes, stages one new patch directory, records an absent-original
checkpoint under `DisabledPatches/EquipmentBackups`, then renames it into place.
It never overwrites existing client archives. Keep the reported checkpoint:

```sh
python -m wxl_equipment.package rollback --client /path/to/client \
  --checkpoint /path/to/checkpoint.json
# Repeat with --apply while WoW is closed.
```

Rollback refuses later edits and retains the removed patch beside the checkpoint.
Preview is read-only. Concurrent external modification during installation is not a
supported workflow; coordinate with other tasks before applying.

## 6. Complete legacy equipment batch

The inventory covers every named BLP below `Item/`, including all component sex
variants and unused legacy appearances. Supply all original archives in game
priority order, excluding installed overlays. It records hashes and dimensions,
deduplicates source content and estimates full-mip output storage before inference.
A zero-length entry in a higher-priority MPQ remains in the original archive; it is
reported separately and never replaced with a texture from an older archive. Other
read/decode failures must be resolved before the batch can be packaged.

```sh
python -m wxl_equipment.batch inventory --workspace /private/work/full \
  --stormlib /private/work/storm/storm.framework/storm \
  --archive /path/to/client/Data/patch-3.MPQ \
  --archive /path/to/client/Data/patch-2.MPQ \
  --archive /path/to/client/Data/patch.MPQ \
  --archive /path/to/client/Data/lichking.MPQ \
  --archive /path/to/client/Data/expansion.MPQ \
  --archive /path/to/client/Data/common-2.MPQ \
  --archive /path/to/client/Data/common.MPQ
HF_HUB_OFFLINE=1 python -m wxl_equipment.batch process \
  --workspace /private/work/full --weights /private/work/realesrnet/model.safetensors \
  --lock models/realesrnet.json --strength 0.35 --recipe conservative
```

Repeat the same processing command to resume. Cache identity includes the source,
model, scale, blend strength, inference implementation and runtime versions. An
interrupted output without its verified report is recomputed. A corrupted completed
cache entry stops the run for investigation. Progress is written to `progress.json`.
Bulk processing stores BLPs and metadata; it does not retain full raw PNGs for every
texture. The smaller pilot remains available for raw model comparisons.

```sh
python tools/audit_batch.py --workspace /private/work/full \
  --output /private/work/full-review
python -m wxl_equipment.batch pack --workspace /private/work/full \
  --output /private/work/full-package
python -m wxl_equipment.package install --client /path/to/client \
  --package /private/work/full-package
```

The audit independently checks every source/output hash, output dimensions, base
alpha mask, each mip pixel, FP32 GPU metadata and bounded RGB difference from the
control. Inspect its deterministic comparison samples before applying the package.
Bulk packages use canonical lowercase asset paths, matching the case-insensitive
MPQ lookup and avoiding directory-spelling differences between host filesystems.
Follow the same preview, stopped-process, checkpoint and rollback workflow above.
A successful offline audit is not a gameplay test.

### Direct-output quality pilot

Extract a small complete set of items with the command in section 1. A pilot
contains at most 128 textures and requires those textures to be already installed
in the equipment patch, so its comparison and before hashes refer to a real baseline.

```sh
python -m wxl_equipment.quality_pilot --workspace /private/work/pilot-input \
  --output /private/work/direct-pilot --client /path/to/client \
  --weights /private/work/realesrnet/model.safetensors --lock models/realesrnet.json
python -m wxl_equipment.trial --client /path/to/client \
  --package /private/work/direct-pilot/package
```

Review every comparison before adding `--apply` with WoW closed. The prepared trial
uses the full neural RGB output resized to 2×, without the bounded-detail filter;
alpha is preserved independently. Body layers remain palettized. Contact sheets
compare original, installed, direct-native/direct-2× and direct-2×/direct-4× variants
at the same display extent. Error metrics measure change, not artistic quality.
`comparison.png` uses labeled bilinear magnification; `comparison-pixels.png`
uses nearest magnification to inspect the stored pixel grid. Preview filtering is
not an asset repair or a simulation of the game's complete sampling pipeline.

For a reviewed 2× asset, `smooth_alpha.resample_alpha` replaces only its independent
alpha with bilinear enlargement of the original mask and BOX-reduced alpha mips.
It preserves the complete deployment header, palette and RGB mip data. This is a
separate contour treatment; conservative inference keeps its exact-alpha default.
The utility rejects other scale factors and missing alpha planes for nonopaque
sources. Review the resulting runtime texture over contrasting backgrounds before
expanding an accepted trial to a larger set.

Keep the trial checkpoint. Preview its restoration with the command below and add
`--apply` only with WoW closed. Restore this trial before using the full patch's
older rollback checkpoint. Later edits and changed backups are refused.

```sh
python -m wxl_equipment.trial --client /path/to/client \
  --rollback /path/to/trial-checkpoint.json
```

Cache BLPs are lossless intermediates. Packaging separately converts body components
to a shared RGB palette plus exact independent alpha, and assigns ARGB8888 as the
GPU format for raw object/NPC payloads. Do not copy cache files directly into the
client. The installer rejects raw pixels mislabeled as DXT1, even with valid hashes.
Body palettes use maximum color coverage across all mips without dithering, keeping
rare accent colors represented. Deployment RGB quantization error is additional to
the inference correction bound and is reported separately by the repair command.

Existing completed packages can be repaired without repeating neural inference:

```sh
python -m wxl_equipment.repack --package /private/work/old-package \
  --output /private/work/corrected-package
```

This verifies every source hash, creates a fresh package, retains each raw object/
NPC mip pixel, and verifies every component mip's alpha. Inspect the generated
repack-report.json for palette RGB error. Use the normal preview and guarded
installation afterward. BLP preferredFormat is consulted for GPU allocation;
successful standalone image decoding does not validate that field. Reference:
[Whoa texture loading](https://github.com/whoahq/whoa/blob/master/src/gx/Texture.cpp).

## 7. Active baked NPC atlases

This workflow is separate from Item components. Inventory the active installed
CreatureDisplayInfoExtra tables; global and locale copies must agree. Existing
bakes in the modern-race overlay take priority over explicit legacy archives.
Preserve their appearance instead of fetching a different Retail source.

```sh
python -m wxl_equipment.npc inventory --workspace /private/work/npc \
  --client /path/to/client --locale ruRU \
  --stormlib /private/work/storm/storm.framework/storm \
  --archive /path/to/client/Data/patch-3.MPQ \
  --archive /path/to/client/Data/patch-2.MPQ \
  --archive /path/to/client/Data/patch.MPQ \
  --archive /path/to/client/Data/lichking.MPQ \
  --archive /path/to/client/Data/expansion.MPQ \
  --archive /path/to/client/Data/common-2.MPQ \
  --archive /path/to/client/Data/common.MPQ
HF_HUB_OFFLINE=1 python -m wxl_equipment.npc process --workspace /private/work/npc \
  --weights /private/work/realesrnet/model.safetensors --lock models/realesrnet.json --recipe direct-smooth
python tools/audit_npc.py --workspace /private/work/npc --output /private/work/npc-review
python -m wxl_equipment.npc pack --workspace /private/work/npc --output /private/work/npc-package
```

Default processing uses `direct-smooth` and restores the whole atlas, including skin and face. An optional
`--protect-face` inventory flag keeps the classic head rectangle at the Lanczos
baseline while preserving alpha. It requires validated 256×256 inputs and is not
a general clothing segmentation model. All outputs use 2× dimensions and the pinned FP32 model. Direct processing stores
full neural RGB with replicated source alpha in its lossless cache; packaging
applies bilinear alpha and BOX alpha mips after runtime RGB encoding. Choose
`--recipe conservative` explicitly for strength 0.35 with exact replicated alpha.

Missing references stop inventory. Investigate each source failure. If files were
already absent from every relevant archive and overlay, `accept-missing` can
explicitly retain their DBC references unchanged: supply each exact virtual path
using `--name`, plus the workspace, StormLib and all source archive arguments.
It requires another absent-source probe, rejects found files, and preserves a
separate missing-source report. Decode failures must not be treated as absent files.

Inspect the audit's full atlases and enlarged head regions across race/sex groups.
The package contains only baked BLPs, plus a manifest accepted by the sibling
modern-race project's existing guarded release installer. Verify source guards,
then preview and apply that installer with the game closed:

```sh
python -m wxl_equipment.npc check-guards --client /path/to/client --package /private/work/npc-package
python /path/to/wxl-modern-races/tools/install_release.py \
  --client /path/to/client --package /private/work/npc-package
# Repeat the reviewed install command with --apply, preserving its rollback.json.
```

Source guards reject changed NPC tables, original archive snapshots and replaced
or newly occupied target paths. Installation uses the existing overlay so current
bakes are backed up instead of depending on uncertain inter-patch precedence.
Keep the release checkpoint for guarded rollback using the same installer. Do not
use the independent Item patch installer for this scoped in-place NPC replacement.
