# Compatibility boundaries

Target: WotLK 3.3.5a build 12340 with the existing WarcraftXL named-patch runtime.
Keep modern race models, helmet bindings, world scales and established Wine/
x87sidecar/mtld3d settings unchanged.

- Body components: the conservative bulk workflow restores native-size sources;
  the selected direct-smooth bulk recipe prepares 2× layers as well as the pilot. The race preparation emits a
  256×256 base skin, which is not proof that the runtime composite is 256×256.
  The build-12340 initializer clamps componentTextureLevel to 6..9 and allocates
  a square sheet of 2^level pixels; compression disabled caps it at 256, and the
  startup path also disables compression when component threading is unavailable.
  With threading/compression enabled, level 9 allows 512×512. A larger input is
  sampled from the mip matching its destination region; it does not enlarge the
  sheet. Raising the CVar above 9 alone cannot produce a 1024 atlas. No compositor,
  executable or settings patch is included. Runtime size and appearance still need
  gameplay evidence. This matches the [reference implementation](https://github.com/whoahq/whoa/blob/master/src/component/CCharacterComponent.cpp)
  and was checked against the supported executable's initializer and CVar caller.
- Objects: weapon, helmet, shoulder, shield, cape, quiver and other named Item BLP
  textures use 2× dimensions without replacing geometry or changing material
  bindings. Textures outside the Item namespace are excluded.
- BLP: lossless inference caches retain BGRA pixels and box-filtered mip chains.
  Deployment preserves the legacy palettized layout for body components, with one
  RGB palette shared by every mip and an independent alpha plane. The direct-smooth recipe applies bilinear source alpha
  only after RGB encoding, with BOX alpha mips; conservative masks remain exact. Maximum
  coverage quantization without dithering retains rare contrasting accents but
  can produce visible gradient banding. RGB quantization to 256 colors introduces error
  beyond the bounded neural correction; report that error separately. Object and NPC payloads
  remain BGRA, with preferredFormat=2 (ARGB8888), never 0 (DXT1). Runtime packages
  contain the full 1172-byte header and validate upload format, mip offsets and
  payload sizes separately from ordinary image decoding.
- Offline race audit: all twenty installed race/sex models expose a body material.
  This is structural evidence only, not a rendering/fit test.
- NPCs: component overlays do not improve clothing already baked into an atlas.
  The separate NPC workflow selects active CreatureDisplayInfoExtra references,
  uses installed bakes first and legacy archives for remaining references, then
  restores the complete atlas at 2×. Clothes, skin and faces share its pixels;
  a precise clothing-only mask cannot be reconstructed from the baked image.
  No new Retail export or rebake is performed. Optional face protection requires
  the validated classic 256-square layout. Larger atlas sampling remains unverified
  in-game and does not enlarge the player character compositor.
- Packaging: equipment uses an independent loose patch. NPC textures use a scoped
  partial release inside the existing race overlay, preserving its active bakes
  as the rollback baseline. The existing race release installer backs up replaced
  files and removes newly added files on rollback; models and DBCs are excluded.
  Installation requires a preview, stopped game, hashes and a rollback checkpoint.
  Settings, original archives, models and account data remain outside the package.
- Small quality trials replace only explicitly listed files in an existing Item
  patch. Before hashes bind the trial to the exact compared deployment; all prior
  files are backed up before writing. Restore the trial before using an older full
  patch checkpoint, whose guard correctly rejects the trial's later modifications.

Outstanding gameplay checks: several races and both sexes, character selection and
world rendering, near/far mip transitions, armor boundaries and robe seams, weapon
wrapping/material effects, relevant NPCs, compositor resolution and frame-time/VRAM
impact. The bulk namespace coverage does not establish in-game quality or increase
the legacy body compositor resolution.

The historical BGRA/DXT1-header deployment failed gameplay: clothing disappeared
and weapon textures were noisy. Successful cache decoding and hash checks did not
exercise the client's GPU-format selection or body compositor. Corrected packaging and the later direct-smooth rollout received a positive user
gameplay report on one setup. The failed deployment itself is not evidence of support,
and exhaustive rendering/performance checks remain outstanding.
