# Contributing

Use Python 3.12+ and Conventional Commits. Run synthetic checks from the checkout:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check tools/export_retail.cjs
git diff --check
```

Tests must run without game files, accounts, a GPU, server or network. Private
integration checks use explicit paths and write only below `_local/` or an external
private workspace. Record tested input hashes, tool versions and evidence level.

Before publishing, inspect the complete staged file list and distribution contents.
Build and check both Python distributions with:

```sh
python3 -m pip install build
python3 -m build --outdir dist
python3 tools/check_distribution.py dist/*.whl dist/*.tar.gz
```

GitHub Actions runs these checks on Python 3.12 and 3.14. The archive checker
enforces the source layout and rejects binary content, links and unsafe paths;
it does not replace manual review of source text and Git history for private data.

Do not include extracted tables, model files, screenshots, generated reports,
runtime binaries, credentials, absolute workstation paths or model weights.
Do not push or publish without an explicit request. Keep public instructions about
current behavior and reproducible usage; machine-specific checkpoints stay private.
