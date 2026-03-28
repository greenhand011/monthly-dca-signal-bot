# Agent Notes

This repository implements a reusable monthly DCA signal bot.

## Key files

- `src/dca_signal_bot/config.py` loads YAML strategy configuration.
- `src/dca_signal_bot/data_fetcher.py` fetches adjusted historical prices with `yfinance`.
- `src/dca_signal_bot/indicators.py` computes drawdown, moving averages, RSI, and 3-year price percentiles.
- `src/dca_signal_bot/strategy_engine.py` applies the rule set and produces the monthly recommendation.
- `src/dca_signal_bot/reserve_state.py` reads and writes `state/reserve_state.json`.
- `src/dca_signal_bot/report_renderer.py` renders the Markdown report.
- `src/dca_signal_bot/feishu_sender.py` pushes the summary to Feishu when enabled.
- `src/dca_signal_bot/cli.py` is the entry point for `python -m dca_signal_bot.cli run`.

## Working rules

- Keep the strategy configuration externalized in YAML.
- Do not hardcode the base monthly amount or allocation weights.
- Preserve the report/state file formats unless there is a strong reason to change them.
- Tests should remain deterministic and should not depend on live market data.
- If you add a rule or metric, update the README and example report too.

## Validation

- `pytest`
- `python -m dca_signal_bot.cli run --dry-run` is useful when no webhook is configured.
