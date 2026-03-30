# Changelog

## Unreleased

- 新增 IBKR 执行建议，使用时区感知的 US/Eastern 交易时段判断
- 新增基于真实汇率数据的美元估算显示，与 RMB 建议金额并列展示
- 保持核心 VOO + QQQM 策略与 fail-fast 市场数据校验不变

## 0.1.0

- `monthly-dca-signal-bot` 首次公开发布
- 通过 `yfinance` 接入 Yahoo Finance 真实行情数据
- 加入严格的数据校验与 fail-fast 行为
- 加入 Markdown 月报生成
- 加入飞书 Webhook 通知
- 加入 GitHub Actions 月度定时与手动触发工作流
- 将生产核心 ETF 切换为 `VOO`
