# Contributing

Use Conventional Commits and keep gameplay evidence distinct from synthetic checks.
Run `python tools/test.py`, `python tools/check_source.py`, `python -m build` and
`git diff --check` from the root environment. Keep source-only fixtures; do not
publish game resources, binaries, model weights, credentials or private reports.
Change shared table composition at `tools/creature_package.py`, druid identities
in races, and riding identities in mounts. Never install a second table redirect.
