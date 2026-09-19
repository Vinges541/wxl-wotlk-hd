# Shared creature package

Races own the druid form catalog, planning and DBC adaptation in
`components/races/src/wxl_races/druids.py` and `druid_planning.py`.
Mounts own riding identities. The root `tools/creature_package.py` performs common
resource conversion and combines both plans into one pair of DBCs and one redirect.
The existing virtual names and DLL remain unchanged to preserve exact signatures.
This packaging detail does not transfer ownership of druid selections to mounts.

```sh
.venv/bin/python hd.py races plan_druid_forms.py --original-dbc /private/original-dbc --retail /private/retail-tables --output /private/druids.json --export-request /private/druid-request.json
.venv/bin/python hd.py shared creature_package.py build --plan /private/mounts.json --druid-plan /private/druids.json --original-dbc /private/original-dbc --raw /private/mount-raw --raw /private/druid-raw --sdk /private/wxl-core/include --stormlib /private/libstorm.so --output /private/combined-package
```

Original DBC inputs must also contain both Tauren character model paths. The
composer applies the race-owned 0.75 world scale after the mount/druid changes.
Verification recomputes the full tables from original inputs and checks every
archive resource. Rebuild the race runtime for the matching preview scale.

The historical mounts commands forward to the root composer. Do not independently
install a second druid-table redirect. Existing legacy druid handoffs are accepted
only under the original pinned hashes; source preparation needs no old packages.
