# RSI 马丁量化交易平台

> 项目路径：`d:/05.project2/1.bquant/rsi`
> 文档版本：2026-03-09

---

## 项目概述

RSI 马丁量化交易平台是一个基于 **OKX 交易所** 的现货量化交易系统，采用 **RSI 超卖信号入场 + 马丁格尔分批补仓 + 多重止盈机制** 的策略逻辑，在震荡行情中持续捕捉超跌反弹机会。

**核心特性：**
- WebSocket 实时 RSI 扫描，毫秒级响应行情变化
- 马丁格尔智能补仓，逐步摊低持仓均价
- 三层风险控制体系（硬止损 / 补仓冷却 / BTC 熔断）
- 全 Web 界面管理，无需命令行操作
- 多用户隔离部署，每个用户独立运行 Bot

**资产安全：** 纯现货交易，无杠杆，不会爆仓，最大亏损为持仓本金。

---

## 功能介绍

### 交易策略

| 功能 | 说明 |
|------|------|
| RSI 超卖入场 | RSI(14, 1m) 低于阈值时市价建仓 |
| 马丁格尔补仓 | 价格下跌时分批加仓，降低均价，最多 6 层（L0~L5）|
| RSI 超买立即止盈 | RSI 进入超买区 + 利润达标时直接卖出 |
| 追踪止盈 | 利润达到启动线后跟踪价格高峰，回撤时自动卖出 |
| 补仓回撤确认 | 瀑布式下跌中等待反弹信号再补仓，避免中途接刀 |
| BTC 联动熔断 | BTC 短时跌幅超阈值时暂停新开仓，规避系统性风险 |

### Web 管理后台

| 页面 | 功能 |
|------|------|
| 仪表板 `/index.html` | 实时持仓列表、总盈亏统计、快捷操作 |
| RSI 扫描器 `/rsi-scanner.html` | 查看所有交易对当前 RSI 值与价格 |
| 交易记录 `/trades.html` | 历史完整交易流水 |
| 盈利统计 `/stats.html` | 分交易对 / 分时段的盈亏分析 |
| 历史回测 `/backtest.html` | 基于历史 K 线模拟策略表现 |
| 配置管理 `/settings.html` | OKX API、全局参数、交易对管理 |

### 风控体系

- **硬止损**：持仓净浮亏超阈值时强制全平（默认关闭，可配置 10%~20%）
- **补仓冷却**：两次补仓之间强制等待，防止瀑布踩踏
- **BTC 熔断**：BTC 短时暴跌时暂停开新仓，已有持仓正常管理
- **多持仓上限**：同时最多持有 N 个仓位（默认 5 个）
- **交易对自动禁用**：下单失败时自动禁用该交易对

---

## 实现方式

### 技术栈

| 层级 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI（Python 3.14）|
| 数据库 | SQLite + SQLAlchemy ORM |
| 交易所接口 | OKX Exchange（ccxt 封装）+ WebSocket |
| 前端 | 原生 HTML + Vanilla JS（无框架依赖）|
| 数据加密 | Fernet 对称加密（API 密钥安全存储）|
| 任务调度 | asyncio（每个用户独立 Task）|

### 核心架构

```
用户浏览器
    │
    ▼
┌──────────────────────────────────────┐
│           FastAPI Web Server          │
│  ┌──────────┐  ┌──────────────────┐   │
│  │ REST API │  │  WebSocket 推送  │   │
│  └──────────┘  └──────────────────┘   │
│  ┌─────────────────────────────────┐  │
│  │         Bot Engine (per user)   │  │
│  │  ┌─────────┐ ┌──────────────┐  │  │
│  │  │ RSI WS  │ │  Trading      │  │  │
│  │  │ Scanner │ │  Engine       │  │  │
│  │  └─────────┘ └──────────────┘  │  │
│  └─────────────────────────────────┘  │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────┐
│     OKX Exchange      │
│  ┌──────────────────┐ │
│  │ REST API 下单    │ │
│  │ WebSocket 实时行情 │ │
│  └──────────────────┘ │
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│   SQLite Database     │
│  · strategy_configs  │
│  · positions         │
│  · trade_logs        │
│  · api_configs       │
└──────────────────────┘
```

### 关键模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 交易引擎 | `app/services/engine.py` | Bot 主循环：RSI 检查 → 止盈/补仓/止损判断 → 执行 |
| RSI 计算 | `app/services/rsi_calculator.py` | Wilder RSI(14) 实现，支持实时逐Tick更新 |
| OKX WebSocket | `app/services/okx_ws_scanner.py` | 订阅行情实时推送，维护 RSI 缓存与价格队列 |
| OKX REST | `app/services/okx_client.py` | ccxt 封装：下单、查询余额、持仓 |
| API 路由 | `app/routers/` | auth / trading / stats / backtest |
| 数据模型 | `app/models.py` | SQLAlchemy 模型定义 |
| 启动入口 | `run.py` | 初始化数据库、启动 FastAPI、唤醒 Bot |

### 数据流（每扫描周期）

```
每 scan_interval 秒：
│
├─ ① 读取 BTC 价格 → BTC 熔断检查
│
├─ ② 遍历所有开仓持仓
│    ├─ 硬止损检查 → 触发则全平
│    ├─ RSI 超买止盈检查 → 触发则卖出
│    ├─ 追踪止盈检查 → 激活后跟踪回撤卖出
│    └─ 马丁补仓检查 → 冷却通过 + 跌幅达标则加仓
│
├─ ③ 遍历所有启用交易对（无仓）
│    └─ RSI 入场信号检查 → 触发则市价买入
│
└─ ④ 休眠等待下一周期
```

---

## 快速启动

### 环境要求

- Python 3.14
- 网络可访问 OKX API（`https://www.okx.com`）

### 安装运行

```bash
cd d:/05.project2/1.bquant/rsi
pip install -r requirements.txt
python3.14 run.py
```

打开浏览器访问 **http://localhost:8000**，首次登录后配置 OKX API 密钥即可开始。

### 首次配置流程

1. 注册 / 登录账户
2. 进入 **配置页面**，填写 OKX API Key / Secret / Passphrase
3. 选择 **模拟盘**（推荐先测试）
4. 在 **交易对管理** 中添加要操作的币种
5. 返回仪表板，点击 **启动 Bot**

---

## 项目结构

```
rsi/
├── app/
│   ├── main.py               # FastAPI 入口，WebSocket 推送，启动迁移
│   ├── models.py             # SQLAlchemy 数据模型（持仓/配置/日志）
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── database.py           # SQLite 连接与会话管理
│   ├── config.py             # Fernet 密钥生成与加密管理
│   ├── routers/
│   │   ├── auth.py           # 注册 / 登录 / Token 鉴权
│   │   ├── trading.py        # 配置、交易对、持仓、日志 CRUD
│   │   ├── stats.py          # 盈利统计接口
│   │   └── backtest.py       # 历史 K 线回测
│   └── services/
│       ├── engine.py         # Bot 核心引擎（扫描主循环）
│       ├── okx_client.py     # OKX ccxt 封装（下单/余额/持仓）
│       ├── okx_ws_scanner.py # WebSocket RSI 实时扫描
│       └── rsi_calculator.py # Wilder RSI 算法实现
├── static/
│   ├── index.html             # 仪表板（持仓列表 + 总览）
│   ├── rsi-scanner.html      # RSI 实时扫描
│   ├── trades.html           # 交易记录
│   ├── stats.html            # 盈利统计
│   ├── backtest.html         # 历史回测
│   ├── settings.html         # 配置管理
│   └── login.html            # 登录页面
├── docs/                      # 文档目录
├── trading.db                 # SQLite 数据库文件（自动生成）
├── .env                       # 环境变量（Fernet 密钥，自动生成）
├── run.py                     # 启动脚本
└── requirements.txt           # Python 依赖
```

---

## 文档目录

| 文档 | 内容 |
|------|------|
| [strategy.md](strategy.md) | 核心策略详解：RSI 入场、马丁补仓、追踪止盈 |
| [risk-control.md](risk-control.md) | 风控方案：硬止损、补仓冷却、BTC 熔断 |
| [configuration.md](configuration.md) | 所有配置参数完整参考与调参建议 |

---

## 参数调优建议

| 场景 | 推荐配置 |
|------|---------|
| 保守（低风险） | 首单 10U，倍率 1.5x，最大 4 层，RSI 超卖 28，开启硬止损 10% |
| **均衡（默认）** | 首单 20U，倍率 2x，最大 5 层，RSI 超卖 30，止盈 1.3% |
| 激进（追求收益） | 首单 50U，倍率 2x，最大 5 层，RSI 超卖 32，补仓更密集 |

详细参数说明与各参数影响分析见 [configuration.md](configuration.md)。

---

## 风险提示

1. **市场风险**：策略依赖 RSI 超卖后反弹的假设，单边下跌行情中马丁补仓会持续亏损
2. **流动性风险**：小币种点差大、深度差，手续费损耗显著
3. **技术风险**：网络中断、交易所 API 故障可能导致订单延迟或失败
4. **本系统为现货策略，无杠杆，最大亏损为持仓本金，不会爆仓**
5. **实盘前务必在模拟盘充分验证参数，实盘资金请量力而行**
