# Checked pipeline

The complete reviewed selection for the pinned donor contains **167 mount displays**:
seven complete new models and 160 revisions of original geometry. This includes
seasonal and ground variants, not 167 distinct mount names. Complete new models
are preferred; another mount of the same animal family is not a substitute.

Coverage: 311 original mounted display references were reviewed. Of these, 124
have no qualifying primary-mesh change, 14 service/test/quest/retired references
lack confirmed same-mount identity, and six have no matching donor display. The
inventory used mounted-aura spells and a supplied source-SQL snapshot; it does not
claim to evaluate a live world's dynamic scripts, spell substitutions or taxi data.
See `catalog/replacements.json` for selected IDs and the compatibility guide for
scope and remaining checks.

All 30 druid forms are owned here after transfer from wxl-modern-races commit
`4981ae97a003b770c4e5801e3dda2c32ac81c907`. Both the verified-asset import and a full
source preparation have produced identical 1903-member packages, including all
534 druid asset bytes, the combined two DBCs, MPQ and redirect DLL. The two creature
tables have a single redirect owner. Other race and equipment overlays are separate.

Checked offline: 39 synthetic discovery, planning/merge, dependency, geometry,
animation hash, installer and distribution tests; 424 actual x86 DLL ABI cases at two addresses; all MPQ members
read by StormLib and an independent reader; texture decoding; runtime dependency
closure; and recomputation of the exact permitted DBC changes. Preparation and
source reproducibility are established for this donor/runtime profile.

A mount-specific adaptation fixes nine unreachable animations caused by the pinned
runtime's insertion into its sequence hash after an ID remap. Eight wind riders
prepare 556→42; the ground Headless Horseman prepares 574→187. Each changes one
inline sequence ID and rebuilds the native hash, preserving its chosen variants.
No shared runtime, tracks, skeletons, external ANIM or druid resources change.

Gameplay is **not verified**. Rider poses, passenger seats, animation transitions,
materials, particles, shadows and performance still need in-game testing.
Private manifests and installation journals carry actual local deployment evidence;
this public source document does not substitute for those checks.
