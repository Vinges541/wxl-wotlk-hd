# wxl-equipment-textures

Local texture restoration for **WoW WotLK 3.3.5a build 12340 with WarcraftXL**.
Upscale clothing, armor, weapons and already-baked NPC atlases using RealESRNet
FP32 on Apple GPU through MLX. Game images stay on your machine.

This repository contains **source code only**. Supply your own game inputs,
StormLib and model weights. No game assets, modified executables, generated texture
packs, credentials or model weights are distributed here.

## Selected workflow

The `direct-smooth` recipe uses full neural RGB at **2× resolution for both body
layers and objects**. It encodes RGB and mip levels first, then enlarges the original
alpha mask with bilinear filtering and reduces its remaining mips with BOX filtering.
This ordering preserves the reviewed RGB palette and smooths clothing contours.

- Explicit source paths and model hashes; no automatic downloads or CPU fallback.
- Resumable, content-addressed processing of the complete named Item namespace.
- Separate NPC atlas processing, preserving its layout and existing appearance.
- Palette BLPs for body layers; correctly labeled ARGB8888 BLPs for objects/NPCs.
- Full mip chains, source/output audits, runtime format checks and guarded deployment.
- Source-only synthetic tests and distribution checks in CI.

The older `conservative` recipe remains available for comparison. It retains native
body-layer dimensions and applies bounded detail at strength 0.35. It produces a
subtler result and is not the selected visual profile.

## Component quick start

Python **3.12+** is required. Inference was exercised on arm64 macOS with MLX
0.32.2; synthetic tests need neither an Apple GPU nor any game files.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '../..[mlx]'
python -m pip install 'realesrgan-mlx @ git+https://github.com/xocialize/realesrgan-mlx.git@52c0fc1044277900b995308095a1f3cc484a3581'
python -m unittest discover -s tests -v
```

Follow [BUILD.md](docs/BUILD.md) to extract original inputs and convert the pinned
RealESRNet weights. After creating the equipment inventory:

```sh
HF_HUB_OFFLINE=1 python -m wxl_equipment.batch process \
  --workspace /private/work/full \
  --weights /private/work/realesrnet/model.safetensors \
  --lock models/realesrnet.json --recipe direct-smooth
python tools/audit_batch.py --workspace /private/work/full --output /private/work/full-review
python -m wxl_equipment.batch pack --workspace /private/work/full --output /private/work/full-package
python -m wxl_equipment.package install --client /path/to/client --package /private/work/full-package
```

The final command is a **read-only preview**. Review the packaged runtime textures
and close WoW before adding `--apply`. Keep its checkpoint for guarded rollback.
An existing different equipment patch is refused; do not overwrite it by hand.
The [NPC workflow](docs/BUILD.md#7-active-baked-npc-atlases) uses its own scoped
package and the modern-race project's release installer.

`process` defaults to `direct-smooth`; use `--recipe conservative` explicitly for
old comparisons. Processing and audits never launch or modify the game.

For body layers with visible gradient bands, pass `--palette-mode median-dither`
to `batch process`. Packing then uses a shared median-cut palette and spatial
Floyd–Steinberg dithering separately on every mip. Alpha and the direct-smooth
mask policy remain independent; object textures stay ARGB8888. The default
`maxcoverage` mode retains the previously accepted encoding. The new mode is
an opt-in quality trial: it can add fine grain or change rare accent colors and
still needs in-game review. See [palette checks](docs/QUALITY.md#palette-mode-trial).

An already-installed loose equipment overlay can be converted to real compressed
MPQs without changing any texture bytes. See [lossless MPQ packaging](docs/MPQ.md)
for full readback verification, size-limited shards and installation without
rollback copies.

## Evidence and limits

A local rollout covered **27,422 equipment textures and 15,403 NPC atlases**. All
installed hashes and runtime-format checks passed; its user subsequently reported
that the result looked okay in game. This is a qualitative report from one setup,
not exhaustive coverage of every item, race, shader pass or mip transition.

Body palettes can show banding in dark gradients, and neural restoration can smooth
painted grain. Texture dimensions do not raise the client's body-compositor limit.
No FPS, VRAM or compositor-resolution improvement is claimed. See
[quality findings](docs/QUALITY.md) and [compatibility](docs/COMPATIBILITY.md).

The public processor uses the same RGB/alpha recipe as that rollout. Its sequential
inference path does not include the workstation-specific batched job orchestration;
processing speed depends on input sizes and hardware. Original inputs should be
retained for future work, especially NPC bakes that have already been replaced.

## Development and license

[Contributing](CONTRIBUTING.md) · [Build instructions](docs/BUILD.md)

Source: [GPL-3.0-or-later](LICENSE). See [dependency notices](THIRD-PARTY-NOTICES.md)
and [model locks](models). Not affiliated with Blizzard. Game assets retain their
owners' rights.
