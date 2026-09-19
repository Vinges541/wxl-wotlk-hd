# Modern mount models

- Read README.md, docs/BUILD.md and docs/COMPATIBILITY.md before pipeline changes.
- Target the same named mount in WotLK 3.3.5a build 12340 and Retail.
  Prefer full new models; otherwise include confirmed revisions of the original
  geometry.
  Resolve Mount/Spell identity and review actual mesh/texture updates; another
  modern mount from the same animal family is not an approved substitute.
  A newer FileDataID, matching display ID or similar filename is discovery evidence,
  never proof of an updated model or a compatible replacement.
- Preserve mount identity, coloration, saddle, armor and faction/class distinctions.
  Record alternatives separately when Retail has no faithful replacement.
- Resolve mounted spell aura 78 through creature entries and server model mappings;
  EffectMiscValue is not a CreatureDisplayInfo ID. Include gender variants and
  shared NPC/model/texture users. Report dynamic and missing mappings explicitly.
- Keep raw M2, SKIN, SKEL, ANIM, BONE and BLP dependencies together with their
  pinned BuildConfig, FileDataIDs and hashes. Do not use OBJ/glTF as runtime input.
- Preparation writes only to fresh private outputs. Keep assets, caches, generated
  files, private reports and binaries out of source commits. Require explicit paths;
  do not depend on sibling checkouts or a particular workstation.
- Own riding mount selections only. Races own druid forms. The root composer owns
  the shared creature package and single table redirect; preserve other overlays.
- Do not change player/NPC world scale to fix rider placement. Review mount attachment
  bones, rider offsets, animation remaps, materials, particles, bounds and shadows.
- Keep discovery, conversion, packaging, deployment and gameplay evidence separate.
  See docs/STATUS.md for the current checked pipeline and its limits; offline
  package verification does not establish gameplay compatibility.
- The installer must preview, verify paths/hashes, reject symlinks and running
  WoW, and support an explicitly selected no-backup policy without removing
  rollback support from reusable tools. Never touch account/WTF data.
- Default tests use synthetic inputs. Use Conventional Commits; no push/publication
  without explicit authorization. Read applicable parent workspace instructions
  when working inside a larger local workspace.
