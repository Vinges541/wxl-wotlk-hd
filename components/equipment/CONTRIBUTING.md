# Contributing

Use Python 3.12 or newer and an isolated environment. Install the base package
with `python -m pip install .` and run `python -m unittest discover -s tests -v`.
The default tests use synthetic inputs, run without MLX, and require no game files,
weights, credentials or network access after dependency installation.

Keep proprietary inputs and generated outputs outside the source tree or under
ignored `_local/`. Do not attach game data, modified binaries, account files or
screenshots to issues or pull requests. Supply a synthetic reproducer, hashes,
dimensions and error text instead. Never include credentials.

For a processing change, compare the RGB recipe, independent alpha and every mip.
Preserve content-addressed resume checks and the runtime BLP format checks.
Installation changes need synthetic coverage for running-process refusal,
unexpected later edits, symlinks and rollback. Never use a live client in tests.
Report numerical equivalence, visual preference and gameplay evidence separately.

Use Conventional Commits (`fix: ...`, `feat: ...`, `docs: ...`). Open a pull request
with the concrete behavior change and relevant validation. The source license is
GPL-3.0-or-later; preserve dependency notices and identify derived code.
