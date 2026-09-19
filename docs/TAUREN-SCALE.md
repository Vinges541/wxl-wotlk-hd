# Tauren scale

Both sexes use 0.75. Creation and selection retain the existing exact-build GLUE
call-site patch, replacing the former male 2/3 and female 0.8 constants. The world
uses `CreatureModelData.dbc` ModelScale (field 4, zero-based), multiplied by 0.75
from the original table. Only exact male/female Tauren character paths match;
other races and animal/druid forms are untouched. NPCs using those Tauren models
also receive the model scale. Server collision data is not modified.

The preview callers explicitly supply unity and the thunk replaces that argument
with 0.75; it does not multiply the world-table coefficient again. Original input
and composed tables are separate. The table adapter accepts only the original or
already-correct value and refuses conflicting changes, making reapplication idempotent.

Rebuild both `components/races/tools/build_runtime.py` output and the shared
creature package. Keep the guarded installer checks and use fresh outputs.
Synthetic table tests and x86 emulation validate the edits, not their visual result.
Check both sexes in character creation/selection, the world, armor and mounted poses
on a legacy client before treating the scale as gameplay-verified.
