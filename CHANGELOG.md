# Changelog

## Unreleased

- Added IBKR execution guidance with timezone-aware US/Eastern session handling
- Added real FX-based USD estimate display alongside RMB recommendation amounts
- Kept the core VOO + QQQM strategy and fail-fast market data validation unchanged

## 0.1.0

- Initial public release of `monthly-dca-signal-bot`
- Added real market data fetching via Yahoo Finance through `yfinance`
- Added strict data validation and fail-fast behavior
- Added Markdown report generation
- Added Feishu webhook notifications
- Added GitHub Actions workflow for monthly runs and manual dispatch
- Switched the production core ETF to `VOO`
