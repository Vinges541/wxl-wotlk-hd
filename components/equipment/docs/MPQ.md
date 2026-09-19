# Lossless compressed equipment archives

`python -m wxl_equipment.mpq` converts an existing, reviewed loose
`Data/Patch-WXL-Equipment.MPQ` directory into real MPQ files. It never reruns
inference or changes BLP bytes. This command owns only `Item/**/*.blp` in that
dedicated overlay; it does not package NPCs, models, locale patches or settings.

## Compatibility profile

The WarcraftXL [named-patch change](https://github.com/WarcraftXL/wxl-core/blob/3990e09b5f80e77351d605dcd48d76b68ab2c2bf/src/patcher/NamedPatchArchives.cpp)
widens the original client's directory-scan patterns to `patch-*.MPQ` and
`patch-%s-*.MPQ`. The native scanner offers both real archives and loose
directories to the existing archive loader. The tool checks these exact strings
at their build-12340 PE addresses and records the executable hash. It does not
patch or execute the client. The current streaming hooks affect async completion;
they do not introduce a new archive format.

The writer uses an explicitly supplied **StormLib 9.30** shared library and a
narrow compatibility profile:

- MPQ v2 (on-disk header version **1**), a 44-byte header at offset zero,
  matching the installed original archives. High-offset fields remain zero.
- Standard 4096-byte sectors and lossless zlib compression mask `0x02`.
  Sectors that do not compress use their original bytes.
- Neutral locale/platform, original internal spelling with MPQ backslashes,
  no encryption, delta patches, file timestamps, signatures or attributes.
- Fewer than **4 GiB per archive**, at most 30,000 payload files per archive,
  and a 32,768-entry hash table for the configured capacity.
- An internal compressed `(listfile)` listing the payload names.

There is no 2 GiB client limit assumed here. The v1 format has 32-bit positions
and sizes; v2 adds wider positions. The installed original archives inspected locally
use header version 1, 4096-byte sectors and hash tables up to 131,072 entries;
`patch.MPQ` is 4,004,713,057 bytes, already above 2 GiB. Equipment compresses into
one archive below 4 GiB, so neither splitting at 2 GiB nor nonzero high offsets
are necessary. The under-4-GiB ceiling is this tool's currently verified profile,
not a claim that MPQ v2 or the client has that general limit. The v2 extension
contains a 64-bit extended-block-table offset and 16-bit upper hash/block offsets;
this narrow reader refuses nonzero extensions rather than claiming to validate
them. Format/API definitions are in
[StormLib.h](https://github.com/ladislav-zezula/StormLib/blob/master/src/StormLib.h).

Names are `Patch-WXL-Equipment.MPQ`, then `Patch-WXL-Equipment-002.MPQ`, etc.
The original basename and prefix are retained. Each internal resource appears in
exactly one shard; their order cannot choose different versions of an Item file.
The inspected modern-race and locale overlays contain no `Item/` members, so
relative ordering with those overlays also cannot affect these resources. The
inspected native comparator at `0x401200` sorts names in descending ASCII-insensitive
order, while the mount loop at `0x405e90` traverses the array backwards and raises
priority after each successful mount. The effective mount order is ascending.
Keeping the original equipment filename therefore retains its position exactly.
Audit third-party overlaps separately before using it on another setup.

## Build and verify

Resolve a compatibility symlink yourself and pass the **physical client path**.
The path guard rejects symlinks rather than weakening checks for the app layout.
Use a fresh private workspace on the same volume, outside the client:

```sh
python -m wxl_equipment.mpq build \
  --client '/path/to/World of Warcraft.app/Contents/Resources/client' \
  --workspace /private/work/equipment-mpq \
  --stormlib /path/to/storm.framework/Versions/9.30.0/storm
```

Inputs remain in place throughout packing and verification. The manifest records
every input path, byte count and SHA-256. Duplicate names under case-insensitive
lookup, matching MPQ name-hash pairs, unsafe paths, symlinks and unexpected
namespaces stop the operation. Sector bounds and reserved table space determine
when the writer starts another shard; final actual sizes are checked too.

Every resource is read back twice: through StormLib and through a separate Python
reader of the encrypted hash/block tables and raw/zlib sectors. That reader checks
all file flags, offsets, neutral locales, table/block coverage, internal listfile
spelling, missing/extra files and case-insensitive lookup. Both outputs must match
the original size and SHA-256. It accepts only this profile, not arbitrary MPQs.

```sh
python -m wxl_equipment.mpq verify \
  --client '/path/to/World of Warcraft.app/Contents/Resources/client' \
  --workspace /private/work/equipment-mpq \
  --stormlib /path/to/storm.framework/Versions/9.30.0/storm
```

## Preview and install without rollback copies

```sh
python -m wxl_equipment.mpq install \
  --client '/path/to/World of Warcraft.app/Contents/Resources/client' \
  --workspace /private/work/equipment-mpq \
  --stormlib /path/to/storm.framework/Versions/9.30.0/storm
```

This is a read-only preview. Add `--apply` only when intending to replace the loose
overlay **without retaining a rollback copy**. WoW must be closed. The installer
rechecks source hashes, staged archives, the executable and protected EXE/DLL/WTF
contents. New shard destinations must be unoccupied. Extra shards are placed
first and contain the same bytes as the still-present loose directory. An atomic
same-volume exchange replaces that directory with the first MPQ. The installed
archives are then completely read back again before the exchanged loose directory
is deleted. No `DisabledPatches`, backup directory or duplicated client is made.

Atomic directory/file exchange is implemented on macOS and Linux. Other platforms
are refused. Do not run the game, updater or another equipment writer during this
operation. If an interruption leaves a partial transaction, inspect the manifest
and `installation.json`; do not delete remaining source files or bypass a refused
retry. Existing verified archives and source hashes allow a guarded recovery.

The only retained build artifacts after successful installation are small JSON
manifests and verification records. This is offline archive and lookup validation;
no real WoW/Wine run, rendering test, startup-time or FPS improvement is implied.

## Synthetic checks

The default test suite exercises the independent reader, malformed-format refusal,
PE-pattern checks, path guards and atomic exchange using synthetic files. Supply
`STORMLIB_TEST_LIBRARY=/path/to/storm` to also run native write/read integration,
deterministic rebuild, multiple shards, preview/apply, running-process refusal,
changed-source refusal and corrupted-archive refusal. No game assets are needed.
