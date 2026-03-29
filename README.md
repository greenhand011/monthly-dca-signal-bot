# monthly-dca-signal-bot

`monthly-dca-signal-bot` is a small, open-source monthly DCA signal bot for a two-ETF core/growth portfolio built around `SPYM` and `QQQM`.

It is designed to:

- Fetch real market data from Yahoo Finance via `yfinance`
- Compute monthly allocation signals with explicit rules
- Render a Markdown report
- Optionally send a Feishu webhook summary
- Persist reserve cash across monthly runs
- Fail fast if the market data is missing, stale, incomplete, or otherwise untrustworthy

## Why only SPYM + QQQM

This repository intentionally keeps the portfolio narrow:

- `SPYM` acts as the broad core holding
- `QQQM` acts as the growth tilt
- A two-ticker setup keeps the strategy easy to review, test, and maintain
- The rule set is easier to explain when only one growth ticker is used for the signal logic

The strategy is not a prediction engine. It is a rule-based execution helper for long-term, monthly discipline.

## Strategy States

The engine can produce the following states:

- `EXTREME_HEAT`
- `HEAT`
- `NORMAL`
- `PULLBACK`
- `DEEP_PULLBACK`
- `CAPITULATION_RECOVERY`

The default configuration uses:

- `base_monthly_rmb: 3000`
- `SPYM: 85%`
- `QQQM: 15%`

When the market overheats, part of the monthly amount is diverted into reserve cash. When the market pulls back, some reserve cash may be deployed.

## Repository Files

Key public-facing files:

- [CHANGELOG.md](./CHANGELOG.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [SECURITY.md](./SECURITY.md)
- [.github/pull_request_template.md](./.github/pull_request_template.md)
- [.github/ISSUE_TEMPLATE/bug_report.yml](./.github/ISSUE_TEMPLATE/bug_report.yml)
- [.github/ISSUE_TEMPLATE/feature_request.yml](./.github/ISSUE_TEMPLATE/feature_request.yml)

## Data Source

The bot uses **Yahoo Finance via `yfinance`** to fetch historical market data.

Important notes:

- This is a research and education data source, not a guaranteed institutional feed
- The bot requires the fetched data to pass validation before any report is generated
- There is no silent fallback to mock, fake, sample, or default market prices in production code

## Data Integrity and Failure Behavior

The bot enforces strict validation:

- The data frame must be non-empty
- The price series must contain a usable `Close` column
- The ticker symbol must be valid
- The history must be long enough for:
  - 200-day SMA
  - 52-week drawdown
  - RSI(14)
  - 3-year price percentile
- The latest market bar must not be stale
- Missing, empty, all-NaN, or too-short data causes a hard failure

If validation fails:

- The CLI exits non-zero
- No normal investment report is generated
- No state file update is written
- If a Feishu webhook is configured, only a failure alert is sent

## Configuration

Main config file:

- [config/strategy.yaml](./config/strategy.yaml)

Example config:

- [config/strategy.example.yaml](./config/strategy.example.yaml)

Environment template:

- [.env.example](./.env.example)

Important fields:

- `base_monthly_rmb`
- `reserve_cap_multiple`
- `core_ticker`
- `growth_ticker`
- `core_weight_normal`
- `growth_weight_normal`
- `feishu_enabled`
- `report_timezone`
- `strategy_name`

### Changing the baseline from 3000 to 6000

Update:

```yaml
base_monthly_rmb: 6000
```

The rest of the strategy stays configuration-driven, including reserve capacity and rule thresholds.

## Local Run

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run the bot

```bash
python -m dca_signal_bot.cli run
```

### What it does

- Fetches live Yahoo Finance data
- Validates the data
- Computes indicators
- Writes `reports/YYYY-MM-report.md`
- Updates `state/reserve_state.json`
- Optionally sends a Feishu summary

## GitHub Actions

Workflow file:

- [.github/workflows/monthly_report.yml](./.github/workflows/monthly_report.yml)

It supports:

- `workflow_dispatch`
- `schedule`

The workflow is designed to fail fast:

- Validation or report-generation failure stops the job
- Report/state commit happens only on success
- A successful run commits the generated report and updated reserve state back to the repository

## Historical Signal Review

Each monthly report now includes a recent month-end review table.

- It shows how the current rules would have behaved on recent monthly snapshots
- It is signal-focused and uses real fetched market history only
- The reserve balance shown in the review is a hypothetical reconstruction from the review window start, not live production state

This helps you inspect the engine without turning it into a heavy backtest.

## Simulation Mode

You can manually simulate a future base amount without changing the live production default.

Example:

```bash
python -m dca_signal_bot.cli run --base-monthly-rmb 6000 --review-months 12
```

- The live default remains `base_monthly_rmb: 3000`
- Simulation mode is clearly labeled in the report and Feishu summary
- Simulation mode does **not** mutate `state/reserve_state.json` by default
- This is intended for safe inspection, not for changing production state

## Feishu Webhook

Set:

```bash
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_KEYWORD=
```

Then enable notifications in `config/strategy.yaml`:

```yaml
feishu_enabled: true
```

On success, the summary includes:

- Date
- Status
- Suggested total investment
- SPYM amount
- QQQM amount
- Reserve cash
- Data source
- Latest market dates
- Validation status
- Report path
- Optional `FEISHU_KEYWORD` prefix if your bot requires a keyword match

On failure, the bot sends only a failure alert, not a normal suggestion.

## Example Report

The file [reports/example-report.md](./reports/example-report.md) is only a layout example.

It is not live market output and must not be mistaken for a real monthly run.

## Troubleshooting

### Data fetch failed

Common causes:

- Yahoo Finance unavailable
- Network blocked or unstable
- Ticker symbol changed
- Market data too stale

What to expect:

- The CLI exits non-zero
- No report is generated
- No normal Feishu recommendation is sent

### Feishu failed

Common causes:

- Missing `FEISHU_WEBHOOK_URL`
- Invalid webhook URL
- Webhook permission issue
- Feishu returned a non-zero business error

What to expect:

- The report is still written if data validation passed
- Feishu failures are surfaced in the Actions log and the step fails
- The report and state artifacts still remain available for inspection

### GitHub Actions permissions issue

If the workflow cannot push report or state updates:

- Make sure repository Actions have permission to write contents
- Make sure the workflow token can push to `main`
- Make sure the remote branch exists and the workflow has access to it

## Testing

```bash
pytest
```

If `pytest` is not installed yet, install dependencies first.

## Risk Disclaimer

This repository is for education and research only. It is not financial advice.

Please remember:

- Market data can be wrong or delayed
- Historical indicators do not predict future returns
- ETF prices are affected by market, currency, and liquidity conditions
- The reserve mechanism changes pacing, not risk itself
