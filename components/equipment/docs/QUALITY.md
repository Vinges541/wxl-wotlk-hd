# Selected profile and gameplay report

The selected public bulk recipe is `direct-smooth`: RealESRNet FP32, full neural
RGB at 2×, then runtime RGB encoding followed by bilinear source alpha and BOX alpha
mips. A local rollout of 27,422 equipment textures and 15,403 NPC atlases passed
file/format checks. The user reported acceptable appearance in game after testing.
This is qualitative evidence from one installation, not an exhaustive quality or
performance benchmark. The earlier missing-clothing/noisy-weapon incident was fixed
by the runtime format and palette changes before this recipe was accepted.

## Palette mode trial

The optional `median-dither` encoding uses a 256-color median-cut palette trained
on all RGB mips, then Floyd–Steinberg diffusion within each two-dimensional mip.
Never dither the concatenated palette-training strip: that loses spatial row
boundaries and carries error across mip levels. Alpha is encoded separately and
the selected bilinear/BOX mask policy is unchanged. Objects and NPC atlases use
ARGB8888 and receive no palette quantization or dithering.

The guild shirt sleeve provides a controlled local example: reproducing the
existing RealESRNet output and historical packing matched the installed BLP hash.
Its neural RGB gradient was smooth, while the max-coverage palette produced
visible bands. The median/dither preview reduced those bands. This is an offline
comparison, not an in-game result or proof of improvement for every texture.
Dithering can introduce fine grain; a frequency-based palette can sacrifice rare
contrasting accents. Review accents, smooth ramps and reduced mip levels together.

Use `batch process --palette-mode median-dither` to record the choice in the run
profile; `batch pack` consumes it. Existing profiles without this field retain
the historical max-coverage encoding and remain reproducible.

## Earlier accepted palette

Dark palettized components can show banding/posterization, observed in two inspected
leather chest variants. Full neural RGB also smooths some grain. Review your complete
items, sex variants, alpha borders and stored mips rather than assuming uniform
improvement. The source CLI reproduces the recipe; the local compiled/batched job's
speed measurements do not characterize this sequential public bulk runner.

The following sections preserve earlier model and conservative-profile comparisons.

## Earlier quality and model evidence

Quality, painted style, symbols, seams and mask preservation take priority over speed.
The pilot compares three models locally; this is not an exhaustive model benchmark.

| Candidate | Role | Observed limitation |
| --- | --- | --- |
| general-x4v3 | Compact comparison baseline | Stronger flattening and hard metal edges in the inspected crops |
| RealESRGAN x4plus | Full GAN comparison | Restores some texture but can change painted highlights/detail |
| RealESRNet x4plus FP32 | Selected conservative profile | Softer output; no proof of recovered ground-truth detail |

Anime-6B is not part of the evaluated or selected workflow. The label “illustration”
alone does not justify applying an anime-trained model to painted game materials.

The conservative bulk profile blends bounded neural detail into a Lanczos/original
baseline at strength 0.35, limiting the neural RGB correction to about 8/255. Body
layers retain their source dimensions. That combination can leave little visible
improvement despite the inference cost; a completed batch is not evidence of a
successful visual upgrade.

The separate direct-output pilot compares the installed baseline with full
RealESRNet RGB at native, 2× and 4× sizes. Its guarded trial uses 2× textures,
including body layers, with independent exact alpha and legacy palette encoding.
In inspected shirt/plate examples, outlines and scales become clearer while fine
grain is smoothed and some geometric lines become wavy; weapon changes are subtler.
The appearance preference and effective compositor sampling still need in-game
confirmation. Larger source images alone do not change the composite atlas size.

On an Apple M3 Pro, MLX 0.32.2, 36 GiB unified memory, RealESRNet FP32 took about
0.065–0.168 seconds for the small body layers and about 0.60 seconds for the 256×128
weapon source. Observed MLX peak allocation reached about 3.13 GiB. These are local
pilot inference timings/allocations, not game VRAM use or frame-time measurements.

The independent synthetic forward check against official RealESRNet weights in
PyTorch CPU FP32 passed: maximum absolute difference 1.91e-6, mean 3.92e-7.
This validates the exercised numerical path, not artistic quality.

Large inputs use exact full-frame evaluation with intermediate materialization. A
synthetic FP32 comparison with the original lazy forward produced a maximum absolute
difference of zero. Real 512×512, 1024×512 and 1024×1024 textures completed locally;
the largest observed MLX allocation was about 9.08 GiB. These checks cover numerical
equivalence and memory feasibility, not in-game results.

## Historical Retail pilot

Pinned profile: Retail 12.1.0.69587, BuildConfig
`c9fa1a64b0170829cc5c5c98c71025c3`.

| ItemID | Result |
| --- | --- |
| 6098 | All eight matching clothing textures are byte-identical |
| 16864 | Matching armor component is byte-identical |
| 16865 | All five matching armor components are byte-identical |
| 25 | Weapon texture is byte-identical; UV and texture types/flags match |
| 19364 | Weapon texture is byte-identical despite a different Retail display ID; UV and material flags match |
| 38 | Different appearance/materials, same dimensions; unresolved, not an approved replacement |

No compatible higher-quality Retail replacement was established for these examples.
This does not establish that no old equipment has been updated anywhere in Retail.

Review raw model sheets beside the original and Lanczos control. Cycle RGB error
(after reducing neural output back to the source size) measures deviation, not
quality: a blurry copy can score well. Inspect symbols, gradients, painted strokes,
UV borders, all mip levels, alpha masks and object effect passes separately.
