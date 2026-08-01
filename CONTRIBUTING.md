# Contributing

EvidenceMesh welcomes focused pull requests with tests and reproducible evidence.

`main` is temporarily a non-installable repository skeleton. Until the draft
alpha pull request is merged, create contribution branches from
`agent/evidencemesh-v0.1`, not from `main`.

1. Create a topic branch from `agent/evidencemesh-v0.1`.
2. Run `uv sync --locked --extra dev --python 3.11`.
3. Add or update tests for behavioral changes.
4. Run `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .` and
   `.venv/bin/pytest`.
5. For ranking changes, run `.venv/bin/evidencemesh benchmark-offline` and
   include the before/after metrics in the pull request.

The validated alpha environment is Ubuntu 24.04 x86_64. CI covers Python 3.11,
3.12 and 3.13. macOS is not yet validated, and native Windows is not supported
for this alpha.

Provider integrations must document authentication, quotas, data handling and
whether the provider is available without a key. Benchmark claims must identify
the dataset, sample, model, configuration, date and hardware.
