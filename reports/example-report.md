# monthly-dca-signal-bot Example Report

> This is a sample layout only. It is not live market output.

**Date**: 2026-03-28  
**Run Mode**: `Production Mode`  
**Market Status**: `NORMAL`

## Data Information

- Data source: Yahoo Finance via yfinance
- Data fetched at (UTC): 2026-03-28T03:15:20Z
- Latest market date for VOO: 2026-03-27
- Latest market date for QQQM: 2026-03-27
- Validation status: PASS

## IBKR Execution Guidance

- Current session phase (US/Eastern): `regular`
- Can submit now: `YES`
- Can likely fill now: `YES`
- Next regular open (Asia/Tokyo): `2026-03-29 22:30 JST`
- Next extended-hours opportunity (Asia/Tokyo): `2026-03-28 05:00 JST`
- Recommended setup: Order Type `LIMIT`, Time in Force `DAY`, Outside RTH `YES`

### Warnings / Notes

- Market orders before regular hours are risky and should not be the beginner default.
- A DAY order is not good forever.
- This project does not place orders automatically.

## FX / USD Estimates

- FX source: Yahoo Finance via yfinance
- FX pair: CNY=X (CNY per USD)
- FX fetched at (UTC): 2026-03-28T03:15:20Z
- FX rate used: `7.2000 CNY per USD`
- FX validation status: PASS
- Total investment: 3000 RMB (~USD 416.67)
- VOO core allocation: 2550 RMB (~USD 354.17)
- QQQM growth allocation: 450 RMB (~USD 62.50)

## Market Data

- VOO current price: `512.34`
- QQQM current price: `468.12`
- QQQM 52-week drawdown: `8.40%`
- QQQM deviation from 200-day SMA: `-1.25%`
- QQQM RSI(14): `54.80`
- VOO 3-year price percentile: `61.20%`
- QQQM 3-year price percentile: `58.90%`
- Current reserve cash: `0 RMB`

## Signal Trigger Details

### Current Asset Snapshot

| Ticker | Current Price | 52W High | Drawdown | SMA200 | Dist. vs SMA200 | RSI(14) | 3Y Percentile |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VOO | 512.34 | 520.00 | 1.47% | 500.12 | 2.44% | 61.20 | 61.20% |
| QQQM | 468.12 | 511.21 | 8.40% | 474.05 | -1.25% | 54.80 | 58.90% |

### Rule Evaluations

| Rule | Triggered | Condition checks | Summary |
| --- | --- | --- | --- |
| EXTREME_HEAT | NO | Drawdown from 52-week high: NO<br>Price vs SMA200: NO<br>RSI(14): NO | QQQM is near its 52-week high, materially above SMA200, and RSI is hot. |
| HEAT | NO | Drawdown from 52-week high: NO<br>Price vs SMA200: NO<br>RSI(14): NO | QQQM is close to its 52-week high, above SMA200, and RSI is elevated. |
| CAPITULATION_RECOVERY | NO | Drawdown from 52-week high: NO<br>Price vs SMA20: NO<br>RSI(14): NO | QQQM is in a deep drawdown but has started to stabilize above SMA20 with RSI recovering. |
| DEEP_PULLBACK | NO | Drawdown from 52-week high: NO<br>RSI(14): NO | QQQM is deeply below its 52-week high and RSI is weak. |
| PULLBACK | NO | Drawdown from 52-week high: NO<br>Price vs SMA200: YES | QQQM is meaningfully below its 52-week high and under SMA200. |

### Decision Path

- triggered_rule: `NORMAL`
- decision_path: `EXTREME_HEAT:NO -> HEAT:NO -> CAPITULATION_RECOVERY:NO -> DEEP_PULLBACK:NO -> PULLBACK:NO => NORMAL`
- triggered_rules: `[]`
- non_triggered_rules: `EXTREME_HEAT, HEAT, CAPITULATION_RECOVERY, DEEP_PULLBACK, PULLBACK`

## 本月建议

- 本月建议总投入金额：`3000 RMB`
- VOO 建议投入金额：`2550 RMB`
- QQQM 建议投入金额：`450 RMB`
- 本月建议动作：`原样投`
- 储备金复用触发：`+0 RMB`

### 原因说明

- QQQM 当前价格 468.12
- 52 周回撤 8.40%
- 200 日偏离 -1.25%
- RSI(14) 54.80
- 未同时满足更强的热度或回撤条件，按基线配比执行。

### 风险提示

- 本报告仅提供规则化辅助决策，不构成投资建议。
- 历史指标不能保证未来收益，ETF 价格、汇率与数据源都可能波动或修正。
- 储备金机制可以平滑节奏，但不会消除市场风险。

### 下次查看建议

建议在下个月首个交易日或下一次月度运行时再次查看；如果 QQQM 的价格结构发生明显变化，也可以提前复核。

## Historical Signal Review (Recent 12 Months)

> Signal-only historical review for the most recent 12 month-end snapshots; reserve balance is hypothetically reconstructed from the review window start at 0 RMB.

| Month | Status | Base RMB | Suggested Total | VOO | QQQM | Reserve Delta | Reserve Balance | Trigger | Reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 2025-04 | NORMAL | 3000 | 3000 | 2550 | 450 | +0 | 0 | NORMAL | Baseline allocation applies. |
| 2025-05 | HEAT | 3000 | 2500 | 2200 | 300 | +500 | 500 | HEAT | QQQM is close to its 52-week high, above SMA200, and RSI is elevated. |
