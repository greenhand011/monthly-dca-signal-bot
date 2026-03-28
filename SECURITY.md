# Security Policy

## Supported versions

The current `main` branch is considered supported.

## Reporting a vulnerability

If you find a security issue, please open a private security advisory on GitHub if available for the repository.

If private reporting is not available, create a public issue only for low-risk, non-sensitive problems.

## Scope

This project:

- Reads public market data from Yahoo Finance via `yfinance`
- Optionally posts summaries to a Feishu webhook URL that you configure
- Writes local report and state files

Do not place secrets in:

- `config/strategy.yaml`
- `state/reserve_state.json`
- generated reports

## Response expectations

Issues that affect data integrity, webhook handling, or repository safety should be treated as high priority.
