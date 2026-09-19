# wxl-wotlk-hd

One source repository for modern races, druid forms, riding mounts and restored
equipment textures on **World of Warcraft 3.3.5a build 12340 with WarcraftXL**.
All components are ordinary directories; no submodules or sibling checkouts.

## Setup

Python 3.12+:

```sh
git clone https://github.com/Vinges541/wxl-wotlk-hd.git
cd wxl-wotlk-hd
python3 bootstrap.py
.venv/bin/python hd.py --help
```

On Windows the virtual-environment interpreter is `.venv\Scripts\python.exe`.
The retained installation workflows are tested on macOS/Linux; Windows gameplay
and installation are not established. MLX texture inference requires Apple Silicon;
processing weights, exporters, StormLib and WarcraftXL are supplied separately.
Setup installs source dependencies; it does not download game data or change a client.

## Components and workflow

- [races](components/races/docs/BUILD.md): twenty player race/sex variants,
  appearance textures, attachments, **all 30 druid form displays** and Tauren scale.
- [equipment](components/equipment/docs/BUILD.md): equipment and baked NPC texture restoration.
- [mounts](components/mounts/docs/BUILD.md): 167 reviewed riding mount displays.
- [Shared creatures](docs/CREATURES.md): one composed creature-table package and redirect.

Run a component tool from the root, for example:

```sh
.venv/bin/python hd.py races prepare_release.py --help
.venv/bin/python hd.py races plan_druid_forms.py --help
.venv/bin/python hd.py shared creature_package.py --help
.venv/bin/python hd.py equipment audit_batch.py --help
```

Tauren men and women use **0.75** in creation/selection previews and in world
model data. The preview EXE patch and composed creature tables must both be rebuilt;
see [scale details](docs/TAUREN-SCALE.md). Model data is derived from original
client tables so rebuilding does not multiply the coefficient repeatedly.

Supply your own original client, pinned Retail exports and required toolchain.
Keep generated resources private. Component build guides describe the remaining
preparation steps and guarded installers; these are not a bundled game download.

## Checks

```sh
.venv/bin/python tools/test.py
.venv/bin/python tools/check_source.py
```

Synthetic tests, exact-build patch verification and archive checks do not establish
in-game rendering. This migration has not been gameplay-tested in a legacy client.
Original repositories remain available; [source revisions](docs/ORIGINS.md).

## License

[GPL-3.0-or-later](LICENSE). Preserve the component third-party notices.
Game assets, binaries, model weights and private build inputs are not distributed.
