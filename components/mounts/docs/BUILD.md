# Preparation and installation workflow

Run component commands from `components/mounts/` using the root virtual environment.
The creature package builder forwards to the suite-level composer. Use explicit paths to your own data; examples below
are placeholders. Outputs are private and must not already exist. Only the explicit installation step changes the client. Raw export writes to
a supplied private exporter profile; discovery and preparation do not change the
client, server or database.

## 1. Original WotLK tables

Supply unmodified build-12340 `Spell.dbc`, `CreatureDisplayInfo.dbc` and
`CreatureModelData.dbc`. Do not take the race project's generated DBC overrides as
original inputs. To extract tables, pass every applicable original archive in
descending precedence, including the client's locale archives. Example fragment:

```sh
mkdir -p /private/work/mounts
wxl-mounts extract --stormlib /path/to/libstorm.dylib \
  --archive /path/to/client/Data/ruRU/patch-ruRU-3.MPQ \
  --archive /path/to/client/Data/ruRU/patch-ruRU-2.MPQ \
  --archive /path/to/client/Data/ruRU/patch-ruRU.MPQ \
  --archive /path/to/client/Data/ruRU/lichking-locale-ruRU.MPQ \
  --archive /path/to/client/Data/ruRU/expansion-locale-ruRU.MPQ \
  --archive /path/to/client/Data/ruRU/locale-ruRU.MPQ \
  --archive /path/to/client/Data/patch-3.MPQ \
  --archive /path/to/client/Data/patch-2.MPQ \
  --archive /path/to/client/Data/patch.MPQ \
  --archive /path/to/client/Data/lichking.MPQ \
  --archive /path/to/client/Data/expansion.MPQ \
  --archive /path/to/client/Data/common-2.MPQ \
  --archive /path/to/client/Data/common.MPQ \
  --output /private/work/mounts/dbc
```

Use your actual locale and archive set. Inputs must be regular files, not loose
`.MPQ` directories. Resolve a known top-level client alias separately, then pass
the physical client root; nested symlinks remain rejected. Extraction checks table
layouts and records source archive names and SHA-256 of the extracted table bytes.
It does not establish original-client authenticity or hash entire source archives.

## 2. Server model references

Aura 78's `EffectMiscValue` is a creature entry. Export the following read-only query
from the applicable AzerothCore world data to **CSV with the shown column headers**:

```sql
SELECT m.CreatureID, m.CreatureDisplayID, m.DisplayScale, m.Probability,
       COALESCE(i.DisplayID_Other_Gender, 0) AS DisplayID_Other_Gender
FROM creature_template_model AS m
LEFT JOIN creature_model_info AS i ON i.DisplayID = m.CreatureDisplayID
ORDER BY m.CreatureID, m.Idx;
```

Use the complete model table so the report can flag other creatures sharing a
mount's model. Keep credentials outside command arguments and reports. The CLI
does not connect to a database or execute SQL. A source-SQL snapshot may be used
for initial discovery, but record that provenance privately: base SQL is not proof
of the live database. Cores using other schemas need an explicit CSV adapter.

```sh
wxl-mounts inventory --dbc-dir /private/work/mounts/dbc \
  --creature-models /private/work/mounts/creature-models.csv \
  --output /private/work/mounts/inventory.json
```

Without `--creature-models`, the command still inventories mounted effects but
marks their creature references unresolved. It never substitutes the creature
entry as a display ID. All template model alternatives and other-gender displays
are retained, including zero-probability entries for conservative impact review.
Missing display/model rows are explicit issues. Wrapper spells can point to other
mount spells; only actual mounted-aura effects are counted, not all collectible items.

## 3. Retail candidates

Supply raw JSON arrays exported by wow.export for `CreatureDisplayInfo` and
`CreatureModelData`, plus `build.json` with `BuildConfig`, `Product`, `VersionsName`.
An existing matching export can be read in place. Supply a semicolon-delimited
community listfile (`FileDataID;path`, no header). Tables must declare the pinned
donor; a newer listfile can contain names unavailable in that donor.

```sh
wxl-mounts discover --inventory /private/work/mounts/inventory.json \
  --retail-dir /private/retail/appearance --listfile /private/retail/listfile.csv \
  --profile dependencies.lock.json --families catalog/families.json \
  --output /private/work/mounts/discovery.json
```

`different-path-candidate` is a metadata difference requiring review.
`same-path-unchecked` can still be an updated asset: raw hashes and visual comparison
are needed. Family candidates are alternatives, never implicit substitutes.
No result is automatically approved. Input hashes make each report traceable;
`build.json` alone does not cryptographically bind its neighboring table exports.

## 4. Review identity and geometry

Use the same named mount's Mount/SourceSpellID and MountXDisplay records. A reviewed
operational variant may share the spell without its own journal record (seasonal
broom/reindeer, ground Headless Horseman or Celestial Steed). Prefer a complete
new model; otherwise include a revised original mesh. Preserve color, saddle,
armor and class/faction identity. The pinned decisions are in
`catalog/replacements.json`; they are not executable asset data.

Compare drawn primary SKIN surfaces with `wxl_mounts.geometry`, including the
Retail display's explicit geoset selection. It ignores vertex/triangle storage
order, winding and degenerate faces, with a 0.001-unit position tolerance and
uniform coordinate normalization. Unused vertices and extra LODs do not establish
an improvement. Review differences and textures; a geometry difference alone
does not establish identity or successful rendering.

The private review JSON has `schemaVersion: 1`, `kind: "same-mount-review"` and a
`displays` entry for every inventoried display, exactly once. Every entry needs
`displayId`, `status` and `reason`; replacements use `status: "replace"` and also
supply `retailDisplayId` and `fileDataId`. Exclusions need an explicit reason.
The planner verifies complete coverage, original table fingerprints, donor model
IDs, conditional-display restrictions and changed display/spell mappings.

```sh
python tools/plan_creatures.py mounts \
  --original-dbc /private/work/mounts/dbc \
  --retail /private/retail/tables \
  --inventory /private/work/mounts/inventory.json \
  --review /private/work/mounts/review.json \
  --output /private/work/mounts/plan.json \
  --export-request /private/work/mounts/request.json
python ../races/tools/plan_druid_forms.py \
  --original-dbc /private/work/mounts/dbc \
  --retail /private/retail/tables \
  --output /private/work/mounts/druids.json \
  --export-request /private/work/mounts/druid-request.json
```

Retail table inputs include CreatureDisplayInfo, CreatureModelData,
CreatureDisplayInfoGeosetData, Mount and MountXDisplay JSON arrays and `build.json`.
An explicit empty geoset selection differs from the default selection; Tree of
Life requires that distinction.

## 5. Export pinned raw resources

```sh
node tools/export_retail.cjs /path/to/wow.export/app.nw \
  /private/work/exporter-profile /private/work/mounts/request.json \
  /private/work/mounts/raw
```

The request contains exact `build` metadata, positive FileDataIDs in `models` and
`textures`, and optionally the five table names listed above in `tables`. Use the
pinned build in `dependencies.lock.json` and its actual CDN configuration. Export
one request at a time into a fresh directory, using a private exporter profile.
Never point this at a shared live UI profile. Its CASC data is valuable input.

Raw output retains per-model FileDataID manifests, SKIN/LOD/ANIM/BLP dependencies
and a status receipt. Only completed records are consumed. Interrupted outputs
must be explicitly classified as partial after validating their completed records;
resume missing assets into another fresh output and supply both `--raw` roots.
Conflicting bytes for one FileDataID, traversal and symlinks are rejected. Preparation
records hashes for the actual source dependency closure; external supplied exports
are trusted inputs, not authenticated by a neighboring `build.json` alone.

## 6. Build and verify

```sh
python tools/creature_package.py build \
  --plan /private/work/mounts/plan.json \
  --original-dbc /private/work/mounts/dbc \
  --raw /private/work/mounts/raw --raw /private/work/mounts/druid-raw \
  --druid-plan /private/work/mounts/druids.json \
  --sdk /path/to/wxl-core/include --stormlib /path/to/libstorm.dylib \
  --output /private/work/mounts/package
python tools/creature_package.py verify \
  --package /private/work/mounts/package \
  --original-dbc /private/work/mounts/dbc --stormlib /path/to/libstorm.dylib
```

Alternatively replace `--druid-plan` with `--druid-package /path/to/verified-handoff`.
That imports the exact 534 druid model/dependency assets from the pinned transferred
package. Its old two DBCs are validated and replaced with the merged tables.
A source build does not require the former race checkout or its prepared assets.
Supply all required raw roots explicitly; byte-identical duplicate FileDataIDs are
accepted. SDK header and compiled redirect hashes are pinned.

The builder performs 424 x86 ABI checks in Unicorn at two load addresses. On hosts
that restrict executable memory, run this offline verification with appropriate
JIT access; do not skip it. Preparation binds display textures to private paths,
filters draw and shadow geosets, preserves dependency aliases and adds only the
selected display/model references to original creature tables. Existing DBC scale,
height and bounds fields are preserved; original world paths are not overwritten.

Nine selected models need a narrow animation lookup repair. Preparation applies
only an otherwise-unreachable native ID remap, then rebuilds the modulo/cumulative
quadratic hash with the same capacity and original chosen sequence slots. It
requires a unique inline sequence with no alias, variants or external AFID for the
changed ID. After all remaining pinned runtime remaps, every existing valid native
choice must remain identical and all native IDs must resolve. This is not a direct
ID-indexed lookup table. Druid resources are not subjected to this adaptation.

Output contains `staged/`, `release-manifest.json`,
`Data/Patch-ModernMounts-HD.MPQ`, and
`Extensions/wxl-modern-mounts/wxl-modern-mounts.dll`. Verification reads every member
using both StormLib and an independent MPQ reader, checks BLP decoding, geometry,
M2-derived SKIN/ANIM/texture closure and byte-exact recomputed DBCs. It requires the
original tables; a self-consistent manifest alone is insufficient.

## 7. Preview and install with WoW closed

```sh
python tools/install_creatures.py \
  --package /private/work/mounts/package --client /physical/path/to/client \
  --stormlib /path/to/libstorm.dylib
# After reviewing the preview, use the same arguments plus:
# --apply --no-backup --report /private/work/mounts/install.json
```

The active locale comes from `WTF/Config.wtf` (or a sole locale data folder).
Preflight checks stock locale/global DBCs, actual EXE/runtime hashes, named MPQ
loading, existing patch storage and collisions with other overlays. The client
path must be physical; reject nested symlinks rather than resolving them away.

The explicit no-backup update publishes verified staged files and replaces the
known transferred druid pair. It removes the old druid redirect before activating
the combined redirect, so both table hooks are never active together. Unknown
existing files and a running/unverifiable WoW process stop writes. Other patches,
root configuration and account/WTF files are checked for preservation. Interrupted
known staging can be resumed with the same package and a fresh journal path.
No rollback snapshots are created and no game is launched.

Finish with the in-game checks in [COMPATIBILITY.md](COMPATIBILITY.md). An installed
hash, complete archive or successful source rebuild is not gameplay evidence.
