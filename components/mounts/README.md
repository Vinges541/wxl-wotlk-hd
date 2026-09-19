# wxl-modern-mounts

Source-only preparation tools for updated Retail riding mounts in
**World of Warcraft 3.3.5a build 12340 with WarcraftXL**.

The reviewed catalog contains **167 mount displays**: seven complete model
replacements and 160 revisions of existing geometry, including seasonal and ground
variants. Full replacements take priority when the same named mount has one.
Unrelated modern mounts are not substitutes. The suite composer also includes the 30 druid forms owned by races.

The pipeline inventories references, exports pinned raw dependencies, prepares
per-display assets, builds and verifies an MPQ plus a small redirect DLL, and
previews or applies a guarded local installation. See [status](docs/STATUS.md) for
what was checked; gameplay compatibility still needs testing in the client.

## Component setup

Python 3.12+; discovery uses the standard library. Preparation additionally needs
Pillow and Unicorn, a caller-supplied StormLib 9.30, clang/lld-link and the pinned
WarcraftXL SDK. Raw export uses Node and a supplied wow.export 0.2.19 application.

Use the [unified setup](../../README.md#setup), then run commands from
`components/mounts/` with the root virtual-environment interpreter.


Use [BUILD.md](docs/BUILD.md) for the complete workflow. Discovery is installed as
`wxl-mounts`; build/export/install scripts are in the source distribution's `tools/`
directory and run from the repository root. Supply explicit input paths and fresh
private outputs. Neither the source distribution nor the wheel contains game assets,
binaries, donor caches or machine-specific reports.

The installer currently accepts one strictly pinned EXE/runtime profile and the
verified legacy druid migration. A different WarcraftXL build or an existing
combined package with different hashes requires a reviewed profile/update adapter.
See [BUILD.md](docs/BUILD.md) before installation.

This component owns riding selections under `WXL/ModernMounts`. Races own
`WXL/DruidForms`; the root composer owns their combined table redirect. Player-race, equipment
and renderer changes remain separate. Per-display model paths avoid replacing
shared legacy files, but NPCs using the exact selected display also see the change.

See [compatibility](docs/COMPATIBILITY.md), [sources](docs/SOURCES.md) and
[contributing](CONTRIBUTING.md). [GPL-3.0-or-later](LICENSE); see
[third-party notices](THIRD-PARTY-NOTICES.md). Game assets are not included or
licensed by this project. Not affiliated with Blizzard.

Related projects: [modern races](https://github.com/Vinges541/wxl-modern-races) and
[equipment textures](https://github.com/Vinges541/wxl-equipment-textures).
