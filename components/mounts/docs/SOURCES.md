# Technical sources

- [WoWDBDefs Spell](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/Spell.dbd),
  [CreatureDisplayInfo](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/CreatureDisplayInfo.dbd),
  [CreatureModelData](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/CreatureModelData.dbd):
  build-12340 WDBC layouts. The reader uses 234, 16 and 28 four-byte fields respectively.
- [AzerothCore aura reference](https://www.azerothcore.org/wiki/spell-aura-reference):
  aura 78 resolves a creature entry, not a display ID.
- [AzerothCore mount handler](https://github.com/azerothcore/azerothcore-wotlk/blob/master/src/server/game/Spells/Auras/SpellAuraEffects.cpp):
  `HandleAuraMounted` chooses a template display and alternate gender; it also
  contains dynamic exceptions that static discovery cannot reproduce.
- [wow.export](https://github.com/Kruithne/wow.export) and its
  [changelog](https://github.com/Kruithne/wow.export/blob/main/CHANGELOG.md):
  raw model exports with dependency manifests, skeletons, animations and textures.
- [WoWDBDefs AnimationData](https://github.com/wowdev/WoWDBDefs/blob/master/definitions/AnimationData.dbd):
  build-12340 fallback, behavior and tier fields for offline animation review.
- [WarcraftXL M2 sequence fixups](https://github.com/WarcraftXL/wxl-modern-m2/blob/main/src/load/M2Fixups.cpp):
  the pinned runtime's curated sequence ID remaps; the native lookup uses hash
  probing, so a missing target ID requires a compatible insertion or preparation.
- [WarcraftXL modern M2](https://github.com/WarcraftXL/wxl-modern-m2): intended
  runtime foundation; not proof that an arbitrary Retail mount already works.
- [Community listfile](https://github.com/wowdev/wow-listfile): FileDataID/name
  discovery. Names and IDs do not establish donor availability or visual equivalence.

Sibling projects `wxl-modern-races` and `wxl-equipment-textures` informed private
asset separation, input hashing and the distinction between offline and gameplay
evidence. The new CLI does not import their modules or require their local paths.
