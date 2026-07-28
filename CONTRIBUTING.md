# Contributing

EvidenceMesh welcomes focused pull requests with tests and reproducible evidence.

1. Create a branch from `main`.
2. Run `uv sync --extra dev`.
3. Add or update tests for behavioral changes.
4. Run `uv run ruff check .`, `uv run ruff format --check .` and
   `uv run pytest`.
5. For ranking changes, run `uv run evidencemesh benchmark-offline` and include
   the before/after metrics in the pull request.

Provider integrations must document authentication, quotas, data handling and
whether the provider is available without a key. Benchmark claims must identify
the dataset, sample, model, configuration, date and hardware.
