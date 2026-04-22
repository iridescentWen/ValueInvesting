# ROADMAP

AI agent for value investing — dashboard-driven stock screener + agent-generated
subjective analysis，覆盖 A 股 / 美股 / 港股。

本文档跟踪**未来要做什么**。当前状态见 [现状快照](#现状快照--r1r8-截至-2026-04-21)。

---

## 参考项目

**[Fincept-Corporation/FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal)**
——C++/Qt 桌面终端，100+ 数据源、37 AI agent、CFA 级 QuantLib、16 券商撮合。

**对标原则**：
- 广度不跟（我们是个人价投研究工具，不是彭博替代品）
- 只抽和**价值投资**相关的子集（DCF、财报时序、moat、peer compare、宏观）
- 技术栈锁定 **Python backend + Next.js frontend**，不迁 C++
- Fincept 的股票数据最终也是 shell 到 Python+yfinance——我们原生 Python，
  直接 pip 装、零额外成本继承同一套源

**License 提醒**：Fincept 采用 **AGPL-3.0**（强 copyleft）。
- 🟢 个人自用 / 不分发：随便抄
- 🟡 复制任何 Fincept 源码 → 本项目一旦通过网络提供服务给他人使用（self-host
  deploy 给家人用也算），**整个项目必须同样 AGPL-3.0 并提供源码**
- 绕开方法：参考 Fincept 的**算法/逻辑**（public domain 财务公式、常见 DCF
  公式本来就不受版权保护），独立用 Python 重写。纯逻辑参考不触发 copyleft

---

## 现状快照 · R1–R8 (截至 2026-04-21)

已落地能力：

- **三市场 screener**：CN / US / HK，按 Graham Number 升序，含 Graham 防御型
  + Buffett 质量闸门（PE ≤ 20 / PB ≤ 3 / GN ≤ 30 / ROE ≥ 10% / MC ≥ 5B）
- **CN 数据源**：Mairui 种子名单 159 支 CSI300 蓝筹（绕过被 geo-block 的
  AkShare 东财端点）
- **US 数据源**：FMP screener + fundamentals
- **HK 数据源**：yfinance + 硬编码 HSI 名单（中文公司名）
- **Agent**：Pydantic AI，模型可切（`LLM_MODEL` env），目前只暴露
  `load_skill` 一个工具，skill 目录下有 `margin-of-safety.md`
- **i18n**：自研轻量方案（zh 默认 / en），覆盖 nav / market / table / dashboard /
  chat / command palette，`/settings` 页切语言，localStorage 持久化
- **Fundamentals 字段**：PE / PB / ROE / 股息率 / 市值（Decimal 序列化成 string）

占位页面（仅 `WorkspacePlaceholder`）：
- `/screener`、`/compare`、`/watchlist`、`/stock/[ticker]`

---

## Phase 1 · 深化 fundamentals （R10–R12）

填满 `FinancialSnapshot` 模型，把财报时序做起来——这是 Phase 2+ 所有页面的数据
基础。

- **[R10] 历史财报时序**
  - `yfinance.Ticker.financials / balance_sheet / cashflow` 拉 4 年年度+季度
  - CN 侧走 `stock_financial_report_sina`（AkShare Sina 端点，境外能通）
  - 入库：DuckDB parquet（OLAP 友好）
  - API：`GET /api/stocks/{symbol}/financials?period=annual&years=5`
- **[R11] DCF 估值模块**
  - 输入：FCF 时序、折现率（WACC 或用户指定）、终值增长率
  - 输出：intrinsic value / 当前价 / margin of safety %
  - 放在 `backend/app/valuation/dcf.py`，pure function，便于测试
- **[R12] Owner earnings 自动计算**
  - Buffett 定义：net income + D&A + 其他非现金 − maintenance capex
  - 把现有 `skills/margin-of-safety.md` 升级成 agent tool `calculate_margin_of_safety(symbol)`

## Phase 2 · 激活占位页 （R13–R15）

把四个 stub 页做成真实功能。

- **[R13] Watchlist**
  - DB schema 已存在（`Watchlist` 模型）
  - 补 REST：`POST/DELETE/GET /api/watchlist`，key 为 `(user=local, symbol, market)`
  - 前端：nav rail 的 ⭐ 入口 + 列表 + add/remove 交互
- **[R14] Compare 页**
  - 输入多支股票 → 并排表格：PE / PB / ROE / Gross Margin / D2E / FCF Yield
  - 附雷达图（shadcn + Recharts）对比质量维度
- **[R15] Stock detail 页** (`/stock/[ticker]`)
  - 财报时序折线（营收 / 净利 / FCF 三图）
  - DCF 卡（展示假设 + intrinsic value + MoS %）
  - 估值敏感性表（WACC × 终值增长率二维网格）

## Phase 3 · 质量与自定义筛选 （R16–R18）

- **[R16] 质量评分**
  - ROE 5 年稳定性（标准差 / 均值）
  - 毛利率趋势（5 年斜率）
  - ROIC（EBIT × (1-t) / 投入资本）
  - 合成分 0–100，显示在 screener / stock detail
- **[R17] 自定义 screener**
  - 前端：拖拽式条件生成器（shadcn Form + Zustand state）
  - 后端：DuckDB 查财报快照 parquet
  - 保存为命名 screen，DB 表 `saved_screens(name, filters_json)`
- **[R18] 行业/板块聚合**
  - 按 GICS sector 聚合估值中位数
  - 输出 "最便宜行业" 榜单（sector PE percentile 最低）

## Phase 4 · 宏观与新闻 （R19–R21）

- **[R19] 个股新闻流**
  - `yfinance.Ticker.news` 免费，按 ticker 聚合
  - CN 侧走 `stock_news_em`（AkShare 东财新闻端点，境外一般能通）
  - 展示在 stock detail 页
- **[R20] FRED 宏观 dashboard**
  - Python `fredapi`（FRED 需要免费 API key）
  - 核心指标：10Y treasury、CPI YoY、失业率、M2
  - 单独页 `/macro`
- **[R21] 财报日历**
  - `yfinance.Ticker.earnings_dates` 拉未来 earnings
  - watchlist 里高亮即将发布的个股

## Phase 5 · Agent 能力扩展 （R22–R23）

- **[R22] 新增 agent tools**
  - `calculate_dcf(symbol, wacc, terminal_growth)`
  - `compare_peers(symbols)`
  - `get_financials_ts(symbol, years)`
  - `get_watchlist()`
  - 让 LLM 能在 chat 里引用这些 pure function 结果
- **[R23] Skill 扩展**
  - `skills/moat-analysis.md`——护城河类型判定（network / switching / scale / brand）
  - `skills/cyclical-analysis.md`——周期股 PE 陷阱识别
  - `skills/circle-of-competence.md`——能力圈判定 checklist

## Phase 6 · 长线 （R24+）

- **[R24] Portfolio 跟踪**
  - 持仓 / 成本 / P&L / 分红再投
  - 输入手工，不接券商
- **[R25] 历史回测**
  - 过去 5 年每月跑当前 screener
  - 跟踪"按 Graham Number 选 top 20"组合 vs 基准（沪深 300 / S&P 500 / HSI）

---

## 数据源扩展策略

**核心洞察**：Fincept 100+ 数据源听起来吓人，但价投真正需要的不多。
Fincept 的股票层本质上是 shell 到 `yfinance`，我们直接 pip 装即可。

| 来源 | 新增用途 | 免费? | 覆盖市场 | 对应 Phase |
|---|---|---|---|---|
| `yfinance.Ticker.financials/balance_sheet/cashflow` | 历史三表 | ✅ | US / HK | Phase 1 |
| `yfinance.Ticker.news` | 个股新闻 | ✅ | US / HK | Phase 4 |
| `yfinance.Ticker.info` 扩展字段 | Margin / D2E / ROIC | ✅ | US / HK | Phase 1 |
| `yfinance.Ticker.earnings_dates` | 财报日历 | ✅ | US / HK | Phase 4 |
| AkShare `stock_financial_report_sina` | A 股三表 | ✅ | CN（Sina 境外通） | Phase 1 |
| AkShare `stock_news_em` | A 股新闻 | ✅ | CN | Phase 4 |
| FRED API (`fredapi`) | 宏观指标 | ✅（需 key） | 全球 | Phase 4 |
| Polygon / Databento | 专业 tick 流 | ❌ 付费 | US | 暂缓 |

---

## 可直接从 Fincept 借用的代码

Fincept 有 **780 个 Python 文件**（`fincept-qt/scripts/`），大量单一职责脚本
可以直接拷贝或做轻量改写。C++ 模块只抄**算法逻辑**，用 Python 重写。

### Python 脚本（可直接复制，注意 AGPL）

| Fincept 路径 | 用途 | 对应 Phase |
|---|---|---|
| `scripts/sec_data.py` | SEC EDGAR 10-K / 10-Q 下载 | Phase 1（US 财报补强） |
| `scripts/economic_calendar.py` | 全球财报 / 宏观日历 | Phase 4（earnings 日历） |
| `scripts/strategies/fincept_engine/universe.py` | 股票 universe 构建 | Phase 3（自定义 screener） |
| `scripts/twelve_data.py` | Twelve Data API 客户端 | Phase 1（US 备用源） |
| `scripts/sec_data.py` + `scripts/bea_data.py` + `scripts/bis_data.py` | 多源宏观 | Phase 4（FRED 扩展） |
| `scripts/agents/finagent_core/` | Agent 架构参考 | Phase 5（agent 扩展） |
| `scripts/ai_quant_lab/qlib_feature_engineering.py` | 微软 qlib 特征工程 | Phase 3（质量评分） |

**策略**：脚本级单文件借用比 fork 整个 `services/` 模块友好——依赖边界清晰、
可逐一验证、不会把 Qt 耦合拖进来。

### C++ 模块（抄逻辑，用 Python 重写）

| Fincept 路径 | 逻辑要点 | 对应 Phase |
|---|---|---|
| `fincept-qt/src/services/backtesting/BacktestingService.cpp` | 回测引擎：时间推进 / 资金管理 / 交易记录 | Phase 6 |
| `fincept-qt/src/services/equity/EquityResearchService.cpp` | 基本面数据编排 / 并行 fetch | Phase 1–2 |
| `fincept-qt/src/datahub/DataHub.cpp` + `TopicPolicy.h` | 订阅 / TTL / 去重调度思路 | Phase 1（缓存策略参考） |

**策略**：C++ 代码量大但本质是 Qt 胶水 + 业务逻辑，业务逻辑用 Python
重写只需几十行；Qt 部分完全抛弃。

### 已内建可直接用的 Python 库（无需抄 Fincept）

- `yfinance` — 基本面 / 历史 / 新闻 / earnings（Fincept 也是这么用的）
- `akshare` — A 股 / HK 股
- `fredapi` — FRED 宏观
- `pydantic-ai` — 已在用

---

## 明确不做（对标 Fincept 但砍掉的部分）

- ❌ **C++/Qt 重写**——Python + Next.js 栈够用
- ❌ **加密货币 / 外汇 / WebSocket tick 流**——不是价投范畴
- ❌ **技术指标**（RSI / MACD / 布林带）——违背价投哲学
- ❌ **券商撮合**（16 broker 集成）——不做交易，只做研究
- ❌ **37 AI agent 人设**——1 个 value agent + 多个 pluggable skill 更清爽
- ❌ **进程内 pub/sub DataHub**——我们 FastAPI + Next.js ISR 已够用
- ❌ **社交 / 论坛 / 用户互动**——定位个人价投研究工具
- ❌ **CFA 全面覆盖 / QuantLib 18 模块**——期权定价、固收估值不是价投核心
