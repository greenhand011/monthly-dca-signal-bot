# monthly-dca-signal-bot

一句话总结：一个基于真实线上行情的月度定投执行助手，默认使用“手动设定总投入 + `VOO / VXUS / QQQM` 独立资产信号 + 固定总额内部分配调整”模式，并附带飞书通知、IBKR 执行建议和美元估算。

## 中文简介

`monthly-dca-signal-bot` 是一个面向长期、按月执行的定投辅助仓库。它不是预测系统，也不是自动交易系统，而是一个强调纪律、可解释性和可复用性的规则化执行助手。

它主要解决这些问题：

- 每个月总投入设多少
- `VOO`、`VXUS` 和 `QQQM` 各自本月应不应该适度高配或低配
- 在总投入固定的前提下，三只 ETF 之间应该怎样调整分配
- 如果你把 `GLDM` 当作保险仓，本月是否值得开仓或补仓
- 如果你在 IBKR 手动执行，现在更适合怎样下单
- 如果你想观察未来把月投基线从 `3000 RMB` 调到 `6000 RMB` 会怎样变化，如何安全模拟而不污染正式状态

## English Introduction

`monthly-dca-signal-bot` is a small open-source monthly DCA execution assistant. It is intentionally not a prediction engine and not an automated trading bot. It fetches real market data, validates it strictly, applies a simple rule set, and produces a monthly recommendation that is easy to review and execute manually.

The current production setup uses `VOO + VXUS + QQQM`, keeps RMB recommendations as the source of truth, and applies independent per-asset tactical signals while holding the monthly total contribution fixed.
It also includes an optional sidecar `GLDM` gold insurance sleeve helper that is evaluated separately from the core monthly engine.

## Why This Project Exists

- 把月度定投执行从情绪判断变成规则执行
- 让每次建议都能回看、能解释、能复核
- 让 GitHub Actions、飞书和本地 CLI 共用同一套可靠逻辑
- 在保持简单策略的前提下，提升执行层可读性

## What This Project Does

- 使用 Yahoo Finance via `yfinance` 获取真实历史行情
- 严格校验 `VOO`、`VXUS`、`QQQM` 的市场数据是否完整、足够新、足够长
- 基于 `VOO`、`VXUS`、`QQQM` 各自独立信号给出资产级高配/低配建议
- 在总投入固定的前提下输出每个资产的基线金额、调整幅度和最终建议金额
- 提供独立的 `GLDM` 黄金保险仓判定：先看是否低于目标仓位，再看是否过热，最后按评分决定本月是否买以及买多少
- 生成 Markdown 月报到 `reports/YYYY-MM-report.md`
- 仅在正式模式成功运行后更新 `state/reserve_state.json`
- 按需发送飞书摘要
- 提供可选的 IBKR 执行建议
- 提供基于真实汇率数据的美元估算
- 支持 GitHub Actions 的 `schedule` 与 `workflow_dispatch`

## What This Project Does Not Do

- 不预测市场
- 不自动交易
- 不连接券商 API 下单
- 不加入卖出逻辑
- 不把 `GLDM` 混入主仓 `VOO / VXUS / QQQM` 月频定投引擎
- 不在市场数据失败时使用 fake/sample/fallback 数据伪造成功
- 不在模拟模式下默认修改正式储备金状态

## Current Production Setup

- 资产组合：`VOO + VXUS + QQQM`
- 正常配比：`VOO 70% / VXUS 20% / QQQM 10%`
- 默认基线月投：`3000 RMB`
- `3000 RMB` 示例：`VOO 2100 / VXUS 600 / QQQM 300`
- `6000 RMB` 示例：`VOO 4200 / VXUS 1200 / QQQM 600`
- 黄金保险仓：`GLDM`，默认作为独立 sidecar 模块，不参与主仓月投拆分
- 黄金仓位评估默认使用 GLDM 持仓股数来推算当前市值，不再手工填写黄金市值
- 默认策略模式：`manual_total_per_asset_signal`
- 储备金上限：`base_monthly_rmb * reserve_cap_multiple`
- 市场数据源：Yahoo Finance via `yfinance`
- 校验策略：fail fast

## Core Workflow

1. 拉取 `VOO`、`VXUS`、`QQQM` 的历史行情
2. 校验数据非空、非过旧、长度足够
3. 对 `VOO`、`VXUS`、`QQQM` 分别计算独立信号
4. 生成每个资产的高配/低配建议，并在固定总投入下做零和调整
5. 按需追加美元估算与 IBKR 执行建议
6. 渲染 Markdown 报告
7. 按需发送飞书摘要
8. 仅在正式模式且成功运行后更新状态文件
9. 若启用 `GLDM` 保险仓模块，则单独评估本月是否值得买入，以及建议买入多少

## Data Integrity and Failure Behavior

本项目对数据真实性要求严格：

- 只使用真实线上市场数据
- `VOO`、`VXUS`、`QQQM` 任一 ticker 抓取失败、为空、全是 NaN、过旧或历史不足时，程序直接非零退出
- 不允许 silent fallback
- 不允许为了让 workflow 成功而生成虚假报告
- 汇率显示属于执行辅助；若 FX 数据失败，不会伪造美元估算

如果市场数据抓取或校验失败：

- 不生成可信投资建议
- 不更新 `state/reserve_state.json`
- 正式通知不会伪装成成功
- 如果配置了飞书，只发送失败告警

## How to Read the Report

报告主要回答四个问题：

- 本月总投入是多少
- 三个资产的基线分配是多少
- 哪个资产建议适度高配，哪个资产建议适度低配
- 每个资产的调整百分比、RMB 变化和 USD 变化是多少

报告中还会包含：

- `信号触发详情`
- `历史信号回顾`
- `黄金保险仓判定`
- `IBKR 执行建议`
- `美元估算`

其中 `RMB` 是策略口径，`USD` 只是执行辅助估算。

## Quick Start

```bash
pip install -r requirements.txt
python -m dca_signal_bot.cli run
```

手动模拟 `6000 RMB` 基线，同时保持正式储备金状态不变：

```bash
python -m dca_signal_bot.cli run --base-monthly-rmb 6000 --review-months 12
```

## How to Run

主配置文件：

- [config/strategy.yaml](/E:/monthly-dca-signal-bot/config/strategy.yaml)

示例配置：

- [config/strategy.example.yaml](/E:/monthly-dca-signal-bot/config/strategy.example.yaml)

环境变量模板：

- [.env.example](/E:/monthly-dca-signal-bot/.env.example)

关键配置项：

- `base_monthly_rmb`
- `strategy_mode`
- `reserve_cap_multiple`
- `core_ticker`
- `secondary_ticker`
- `growth_ticker`
- `core_weight_normal`
- `secondary_weight_normal`
- `growth_weight_normal`
- `feishu_enabled`
- `report_timezone`
- `execution_guidance_enabled`
- `user_timezone`
- `preferred_order_type`
- `preferred_tif`
- `suggest_outside_rth`
- `gold_sleeve.enabled`
- `gold_sleeve.current_total_portfolio_value_rmb`
- `gold_sleeve.current_gldm_shares`
- `gold_sleeve.target_weight`
- `gold_sleeve.max_weight`

## GitHub Actions

工作流文件：

- [.github/workflows/monthly_report.yml](/E:/monthly-dca-signal-bot/.github/workflows/monthly_report.yml)

它支持：

- `schedule` 定时运行
- `workflow_dispatch` 手动运行
- 手动传入 `base_monthly_rmb`
- 手动传入 `review_months`
- 手动传入 `current_total_portfolio_value_rmb`
- 手动传入 `current_gldm_shares`
- 手动传入 `current_total_portfolio_value_rmb`
- 手动传入 `current_gldm_shares`

行为特点：

- 先跑测试，再生成报告
- 报告生成失败会直接中止
- 产物会上传，便于排查
- 只有正式模式成功时才提交 `report` 和 `state`
- 模拟模式会明确标记，且默认不改正式储备金状态

在 GitHub Actions 的 **Run workflow** 面板里，`current_total_portfolio_value_rmb` 和 `current_gldm_shares` 都是可选输入：

- `current_total_portfolio_value_rmb`：当前总资产 RMB，例如 `100000`
- `current_gldm_shares`：当前 GLDM 持仓股数，例如 `0`、`12.5`、`25.6`

如果留空，系统会继续跑市场层判断，但黄金仓仓位相关字段会显示“部分缺失/不可用”。

## Feishu Notification

飞书摘要默认包含：

- 日期
- 运行模式
- 状态
- 总投入
- `VOO` / `VXUS` / `QQQM` 金额
- 储备金变动与余额
- 数据来源
- 最新市场日期
- 校验状态
- 原因
- 报告路径
- `GLDM` 黄金保险仓建议
- 简版 IBKR 执行建议
- 简版美元估算

如果机器人需要关键字，可配置：

```bash
FEISHU_KEYWORD=你的关键字
```

## Simulation vs Production

正式模式：

- 使用 `config/strategy.yaml` 中的默认基线
- 成功时会更新正式储备金状态

模拟模式：

- 通过 `--base-monthly-rmb` 触发
- 只放大或缩小总投入，不自动切换另一套 ETF 搭配
- 当前默认无论 `3000` 还是 `6000`，都使用 `70/20/10`
- 默认不修改正式储备金状态

## GLDM Gold Sleeve

`GLDM` 是一个单独的黄金保险仓辅助模块，不属于主仓 `VOO / VXUS / QQQM` 月频定投引擎。

它的决策顺序是：

1. 先看当前黄金仓位是否低于目标仓位
2. 再看是否触发过热过滤
3. 最后用简单评分判断本月是否值得补仓

当前黄金市值默认由持仓股数自动推算：

- `current_gold_value_usd = current_gldm_shares * GLDM_price_usd`
- `current_gold_value_rmb = current_gold_value_usd * USDCNY_rate`
- `current_gold_weight = current_gold_value_rmb / current_total_portfolio_value_rmb`

买入金额不是固定值，而是基于目标缺口计算：

- `target_gold_value = current_total_portfolio_value_rmb * target_weight`
- `target_gap_value = max(target_gold_value - current_gold_value_rmb, 0)`
- 若评分不足则不买
- 若评分达到区间，则买入目标缺口的 `25% / 50% / 100%`

注意：

- `GLDM` 使用 Yahoo Finance via `yfinance` 的 `GLDM` 调整后收盘价作为主判断价格代理
- 可选宏观因子如果缺失，不会伪造数据，也不会让整个主仓月报崩溃
- `GLDM` 只是保险仓择时补仓提示，不是自动交易
- GitHub Actions 手动运行时可以输入 `current_total_portfolio_value_rmb` 和 `current_gldm_shares`，二者都可选填；如果没有填，报告会显示部分输入缺失并仅保留市场判断
- `current_total_portfolio_value_rmb` 建议填最近一次可确认的总资产 RMB
- `current_gldm_shares` 建议填券商里当前 GLDM 持仓股数，例如 `0`、`12.5`、`25.6`

## Example Output

- [reports/example-report.md](/E:/monthly-dca-signal-bot/reports/example-report.md)

该文件只是示例版式，不代表实时行情。

## Repository Structure

```text
monthly-dca-signal-bot/
├─ README.md
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ SECURITY.md
├─ config/
├─ reports/
├─ src/dca_signal_bot/
├─ tests/
└─ .github/workflows/
```

## Roadmap

- 保持策略简单且可解释
- 保持数据校验严格
- 继续提升通知与报告可观察性
- 保持模拟模式安全

## Disclaimer

本仓库仅用于研究和教育，不构成投资建议，也不是券商执行软件。真实行情与汇率数据可能延迟、缺失或修订，请在实际执行前先查看生成的报告。
