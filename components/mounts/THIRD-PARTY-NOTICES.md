# Third-party notices

The project is GPL-3.0-or-later. Source design was informed by the GPL-licensed
`wxl-modern-races` and `wxl-equipment-textures` projects. The standalone readers
use documented WDBC layouts and the StormLib API; no game data is redistributed.

External tools are supplied separately: WarcraftXL / wxl-modern-m2 (GPL-3.0-or-later),
wow.export (MIT), StormLib (MIT). Their licenses remain with their respective projects.
Game models, textures and tables remain the property of their respective owners;
this project's license does not grant rights to those assets.

Adapted source (GPL-3.0-or-later): generic M2 readers/staging/skeleton assembly from
`wxl-modern-races` commit `752e2148a97d3527625986467c36bb0719ab1289`; druid planning,
creature adaptation, MPQ helpers, PE inspection, redirect and ABI checks from its
commit `4981ae97a003b770c4e5801e3dda2c32ac81c907`. Source fingerprints and modification
scope are recorded in `catalog/model-reader-source.json` and
`catalog/creature-adapter-source.json`. MPQ helpers originated in
`wxl-equipment-textures`; the PE inspector derives from WarcraftXL code, copyright
2026 WarcraftXL, adapted by wxl-modern-races contributors. The source-only druid
handoff is preserved privately; no Blizzard assets are included in these copies.

The sequence-remap profile and the simulation in `animations.py` follow
WarcraftXL's GPL-3.0-or-later `src/load/M2Fixups.cpp` (copyright 2026 WarcraftXL).
The native hash preparation and regression tests are new adaptation code.
