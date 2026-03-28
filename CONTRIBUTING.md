# Contributing

Thanks for considering a contribution.

## How to help

- Open an issue for bugs or feature ideas
- Keep changes small and focused when possible
- Update tests when changing strategy logic or data validation
- Update `README.md` if user-facing behavior changes

## Before you submit a PR

Run the checks that are available in your environment:

```bash
python -m compileall src tests dca_signal_bot
pytest
```

If `pytest` or network-dependent tests are unavailable locally, describe that in the PR so reviewers know what was exercised.

## What to avoid

- Fake or sample data paths in production code
- Silent fallbacks when market data is missing or stale
- Unexplained strategy changes

## Code style

- Keep the runtime dependency set small
- Prefer explicit validation and clear error messages
- Preserve the public report format unless you are intentionally changing it
