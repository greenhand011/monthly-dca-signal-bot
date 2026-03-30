# monthly-dca-signal-bot

一句话总结：一个基于真实线上行情的月度定投执行助手，默认围绕 `VOO + QQQM` 生成 RMB 主导的月度建议，并附带飞书通知、IBKR 执行建议和美元估算，全部在 fail-fast 校验通过后才输出。

## 中文简介

`monthly-dca-signal-bot` 是一个面向长期、按月执行的定投辅助仓库。它不是预测系统，也不是自动交易系统，而是一个强调纪律与可复用性的规则化执行助手。

它解决的是这样的问题：

- 每个月该投多少
- `VOO` 和 `QQQM` 如何分配
- 当前市场状态是正常、过热，还是回撤
- 如果你打算在 IBKR 执行，当前更适合什么下单方式
- 如果你想提前对照未来的 `6000 RMB` 基线做观察，应该如何安全地模拟

仓库面向的是希望用简单规则长期执行定投的人，尤其是：

- 想保留策略纪律，而不是追逐短线预测的人
- 希望用 GitHub Actions 定时生成报告的人
- 想把报告同步到飞书群的人
- 想把 RMB 策略建议和 IBKR 的 USD 执行估算放在一起看的人

## 英文简介（English Introduction）

`monthly-dca-signal-bot` is a small open-source monthly DCA execution assistant. It is intentionally not a prediction engine and not an automated trading bot. Its job is to fetch real market data, validate it strictly, apply a simple rule set, and produce a monthly recommendation that is easy to review and act on.

The production setup currently targets:

- `VOO` as the broad core holding
- `QQQM` as the tactical growth tilt
- `85% / 15%` default allocation in normal conditions

The repository is designed for people who want a simple, repeatable monthly workflow with real-data validation, readable reports, Feishu notification support, and optional execution guidance for IBKR users.

## 为什么存在

- 让月度定投决策保持规则化，而不是情绪化
- 让推荐过程可审计
- 让正式默认配置足够简单，便于长期维护
- 让报告对未来的自己和协作者都更容易阅读

## 项目做什么（What This Project Does）

- Fetches real historical market data from Yahoo Finance via `yfinance`
- Validates that market data is usable, recent, and complete
- Computes the existing monthly signal logic for `VOO + QQQM`
- Produces a Markdown report under `reports/YYYY-MM-report.md`
- 只有在运行有效且处于正式模式时才更新储备金状态
- 启用后发送简洁的飞书摘要
- 提供可选的 IBKR 执行建议
- 提供基于真实汇率数据的可选美元执行估算
- 支持 GitHub Actions 的 `schedule` 和 `workflow_dispatch`

## 项目不做什么（What This Project Does Not Do）

- 它不预测市场
- 它不自动下单
- 它不登录 IBKR
- 它不添加卖出逻辑
- 它不会在正式运行中使用 fake / sample 市场数据
- 它不会在抓取失败时悄悄退回到伪造价格
- 它不会因为显示语言变化而改变实际推荐语义

## 当前生产配置（Current Production Setup）

- 核心 ETF：`VOO`
- 增强 ETF：`QQQM`
- 正常配比：`VOO 85%` / `QQQM 15%`
- 基线月投金额：`3000 RMB`
- 储备金上限：`base_monthly_rmb * reserve_cap_multiple`
- 市场数据源：Yahoo Finance via `yfinance`
- 正式模式校验风格：fail fast

## 核心流程（Core Workflow）

1. 拉取 `VOO` 和 `QQQM` 的历史行情
2. 校验数据非空、足够新、长度足够
3. 计算指标并应用现有规则
4. 生成 RMB 口径的月度建议
5. 视需要把 RMB 建议换算成估算 USD，方便 IBKR 执行
6. 视需要加入 IBKR 执行建议
7. 渲染 Markdown 报告
8. 视需要发送飞书摘要
9. 仅在正式模式且校验通过后更新 `state/reserve_state.json`

## 数据哲学与校验规则（Data Philosophy and Validation Rules）

本项目对数据质量的要求非常严格：

- 只使用真实线上数据
- 不使用 mock 或 fallback 市场价格
- 数据缺失时不允许静默成功
- 如果 `VOO` 或 `QQQM` 数据过旧、为空或不完整，则不生成报告
- 如果汇率抓取失败，则不显示 USD 估算
- 校验失败时不允许修改状态文件

校验失败会让程序以非零退出码结束。若启用了飞书，失败路径只会发送失败告警，不会发送正常建议。

## 如何阅读报告（How to Read the Report）

Markdown 报告的目标是让你快速回答四个问题：

- 现在是什么市场状态
- 本月建议投多少
- `VOO` 和 `QQQM` 各投多少
- 为什么会得到这个结果

报告还会包含：

- `信号触发详情`，展示每个阈值是否触发
- `IBKR 执行建议`，提供按交易时段感知的执行建议
- `美元估算`，提供 RMB 到 USD 的执行便利信息
- `历史信号回顾`，展示最近月末快照的观察结果

`RMB` 仍然是策略的唯一口径。`USD` 只是执行辅助估算。

## 快速开始（Quick Start）

```bash
pip install -r requirements.txt
python -m dca_signal_bot.cli run
```

To simulate a future `6000 RMB` baseline without mutating production reserve state:

```bash
python -m dca_signal_bot.cli run --base-monthly-rmb 6000 --review-months 12
```

## 配置说明（Configuration）

Main config:

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
- `execution_guidance_enabled`
- `user_timezone`
- `preferred_order_type`
- `preferred_tif`
- `suggest_outside_rth`

## 如何把基线从 3000 改到 6000

Update:

```yaml
base_monthly_rmb: 6000
```

这就是正式策略的实际改动。如果你只想观察效果、但不想改动正式状态，请使用 CLI 的模拟参数：

```bash
python -m dca_signal_bot.cli run --base-monthly-rmb 6000
```

## GitHub Actions 用法

工作流文件：

- [./.github/workflows/monthly_report.yml](./.github/workflows/monthly_report.yml)

它支持：

- 用 `schedule` 做月度定时运行
- 用 `workflow_dispatch` 做手动触发
- 通过手动输入支持模拟模式和回顾窗口

行为：

- 校验失败会直接终止任务
- 报告生成先于通知发送
- 只有成功时才上传报告与状态产物
- 模拟运行会明确标记，默认不修改正式储备金状态

## 飞书通知概览

如果你在配置中启用飞书并设置 `FEISHU_WEBHOOK_URL`，程序会发送一条简洁摘要，包含：

- 日期
- 状态
- 建议总投入
- `VOO` 金额
- `QQQM` 金额
- 储备金变化
- 数据来源
- 最新市场日期
- 校验状态
- 报告路径

可选的关键字前缀支持：

```bash
FEISHU_KEYWORD=你的关键字
```

如果飞书拒绝请求，程序不会假装发送成功。

## 模拟模式与正式模式

### 正式模式

- 使用配置中的 `base_monthly_rmb`
- 可能更新 `state/reserve_state.json`
- 代表正式生产建议路径

### 模拟模式

- 通过 `--base-monthly-rmb` 触发
- 适合观察未来 `6000 RMB` 基线
- 在报告和飞书摘要中会明确标记
- 默认不会修改正式储备金状态

## 仓库结构

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

## 示例输出

- [reports/example-report.md](./reports/example-report.md)

该文件只是示例版式，不是实时市场输出。

## 路线图 / Next Steps

- 在策略演进时保持报告仍然易读
- 保持数据校验严格
- 保持通知链路可观察
- 保持模拟模式安全且标记清晰
- 保持公开文档与真实生产行为一致

## 故障排查

### 数据抓取失败

常见原因：

- Yahoo Finance 不可用
- 网络被阻断或不稳定
- ticker 无效
- 最新行情过旧

预期行为：

- CLI 以非零退出码结束
- 不会生成伪造报告
- 不会更新状态文件
- 若启用了飞书，会收到失败告警

### 飞书失败

常见原因：

- `FEISHU_WEBHOOK_URL` 为空或未配置
- Webhook 拒绝了请求体
- 机器人需要关键字，但未设置 `FEISHU_KEYWORD`

预期行为：

- 失败会在日志中可见
- 即使市场数据成功，通知失败也不会被悄悄吞掉

### GitHub Actions 权限不足

常见原因：

- 工作流没有回写仓库的权限
- 分支受保护
- Runner 上没有可用的 GitHub 凭证

预期行为：

- 工作流清晰失败
- 报告和日志仍然可以作为产物查看

## 免责声明

本仓库仅用于研究和教育，不构成投资建议，也不是券商执行软件，更不保证未来收益。真实行情与汇率数据可能不完整、延迟或修订。请在执行前先查看生成的报告。
