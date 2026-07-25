# Alpaca 国际账户与入金 — 香港银行卡实操指南

> 基于 2026-05-27 对 Alpaca 文档和实际开户流程的调研。

## 核心结论

**Alpaca 支持国际账户，香港汇丰卡可以通过 SWIFT 电汇入金。关键卡点在 KYC 时的「税务居住地国家」选项。**

## 入金方式对比

| 方式 | 适用账户 | 香港银行卡能否用 |
|------|---------|:---:|
| **ACH（美国银行转账）** | 需美国银行账户 | ❌ |
| **国际电汇 SWIFT** | 支持国际账户 | ✅ |
| **Plaid 绑卡** | 仅限美国银行 | ❌ |

## 开户关键步骤

1. **打开真实账户（不是 Paper Trading）**：去 `app.alpaca.markets` 走真实开户流程
2. **KYC 关键字段**：`Country of Tax Residence` — 下拉框里有没有 **Hong Kong** 选项决定一切
3. **如果 HK 可选** → 选 HK，提交 W-8BEN 表（非美国纳税人标准流程），通过后绑汇丰 SWIFT 入金
4. **如果只有 China (Mainland)** → 可能被拒（大陆居民开户有已知困难）

## Alpaca 文档证据

### 支持国际账户

- Alpaca 有专门的 **"International (Non-US Tax Residents)"** 帮助分类
- 支持 **W-8BEN** 表：非美国纳税人开户标准流程
- 文档路径：`docs.alpaca.markets/us/docs/international-accounts.md`

### 支持 SWIFT 电汇

出处：`docs.alpaca.markets/us/docs/funding-accounts.md`

> "Alpaca supports international wire transfers and the API endpoint is the same as the US domestic case. You need to provide the SWIFT code and account number of the beneficiary, as well as the address and name of the receiving bank."

### Country Info API

Alpaca Broker API 有 `GET /v1/countries` 端点返回支持的国家列表（含 risk rating）。零售账户的支持国家列表未在文档中公开列出，需通过实际开户流程确认。

## 关键区分

- **银行卡在哪里 ≠ 税务居民身份**：汇丰 HK 卡在国际银行体系内，但 Alpaca KYC 看的是你声明自己是哪里的税务居民
- **Paper Trading ≠ 真实账户**：Paper Trading 不需要 KYC/入金，真实账户才需要
- **Alpaca Trading（零售）vs Alpaca Broker API（机构）**：文档中看到的大部分 Funding API 文档是针对 Broker API 客户的。零售账户的入金流程在 Web UI 上完成，不走 API。

## 替代方案

如果 Alpaca 零售账户对 HK 居民有限制，更可行的路径：

1. **盈透 IBKR 香港**：香港银行→IBKR HK，同地区资金流转无障碍，支持美股交易
2. **辉立/耀才等香港本地券商**：同样无障碍
3. **Charles Schwab International**：接受国际客户，但最低存款要求较高
