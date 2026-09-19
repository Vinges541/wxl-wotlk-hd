# Compatibility and acceptance

The pinned selection has been prepared and verified offline, including identical
import/source builds. In-game compatibility is not established. See STATUS.md and
the private installation journal for their separate evidence.

| Area | Required evidence before release |
| --- | --- |
| Identity | Original and donor compared side by side; color, saddle, armor, faction/class distinctions retained |
| Dependencies | Pinned BuildConfig and complete raw FileDataID closure; missing/encrypted assets stop preparation |
| Geometry | Valid M2/SKIN counts, indices, geosets, skeleton and supported material/shader features |
| Movement | Idle, walk, run, jump, landing, swim, flight/takeoff where applicable; animation/fallback coverage |
| Rider | Correct seat/attachment and pose for both sexes of all ten WotLK races; no player world-scale workaround |
| Special mounts | Passenger seats, vehicles, effects, special transforms and class mounts reviewed separately |
| World impact | Shared model paths, texture paths and display users reviewed; dynamic server references accounted for |
| Runtime | Actual installed EXE/DLL hashes and loader behavior checked; profile metadata alone is insufficient |
| Rendering | In-game materials, particles, shadows, texture memory and crowd performance |
| Packaging | Dedicated ownership, archive readback, hashes and collision checks; no unrelated patch edits |

The inventory follows explicit mounted-aura effects and supplied template models,
including alternate genders. It does not evaluate SQL spell overrides, scripts,
holiday/skill/faction substitutions, spawn-specific models, taxi-node data or the
live server's random selection. Other-creature references are a conservative
signal, not a complete impact audit. A display used by a mount can also be an NPC;
even a path with one known display is not automatically safe to replace.

The shared environment's race and equipment improvements remain owned by those
projects. Preserve modern player models and the existing renderer workarounds until
replacement behavior is demonstrated in game. A successful export, parser test or
conversion is not an in-game result.

## Prepared scope and in-game checks

The catalog records 167 displays: seven complete replacements (five kodo colors,
Charger and Thalassian Charger), then 160 revisions where the same mount has no
reviewed complete remake. Revisions range from small surface corrections to more
extensive changes such as gryphons, Ashes of Al'ar and the Amani War Bear. Geometry
change is not necessarily a large visual improvement. Seasonal broom/reindeer and
ground Headless Horseman/Celestial Steed variants are included explicitly.

Each selected display points to a private cloned model row. All original model
rows and legacy resource paths remain present; displays outside the plan retain
their original references. An NPC sharing the exact changed display also changes,
whereas another display merely sharing its legacy model path does not. Supplied
server template/gender references are an impact inventory, not an exhaustive live
NPC audit. Original display/model scales and DBC height/bounds fields are preserved.

For gameplay validation, prioritize the new kodos and both paladin Chargers, then
a ground and flying representative from each revised family. Check idle, movement,
jump, water, takeoff/landing, rider alignment and shadows. Test all mammoth and
X-53 passenger seats with occupants, class/faction colors, seasonal transforms and
Celestial Steed/Headless Horseman ground-to-flight transitions. Check all druid
forms, especially Tree of Life's explicit empty extra-geoset selection. Use the
private report's display/spell list to record exact failures and reproduction steps.

All prepared models have a rider attachment where used as mounts, but structural
presence does not prove the seat looks correct. Animation payload availability and
valid indices likewise do not prove client transitions, shader appearance or
particle behavior. Keep renderer workarounds until an in-game replacement is shown.
