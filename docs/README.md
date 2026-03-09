# RSI 马丁量化交易平台 — 文档目录

> 项目路径：`d:/05.project2/1.bquant/rsi`
> 技术栈：Python 3.14 + FastAPI + SQLite + OKX WebSocket

---

## 文档列表

| 文档 | 内容 |
|------|------|
| [strategy.md](strategy.md) | 核心策略说明：RSI 入场、马丁补仓、追踪止盈、超买止盈 |
| [configuration.md](configuration.md) | 所有配置参数完整参考表与调参建议 |
| [risk-control.md](risk-control.md) | 风险控制方案：硬止损、补仓冷却、BTC 熔断 |

---

## 快速启动

```bash
cd d:/05.project2/1.bquant/rsi
pip install -r requirements.txt
python3.14 run.py
# 打开浏览器访问 http://localhost:8000
```

## 项目结构

```
rsi/
├── app/
│   ├── main.py               # FastAPI 入口，WebSocket，启动迁移
│   ├── models.py             # SQLAlchemy 数据模型
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── database.py           # SQLite 连接
│   ├── config.py             # 加密密钥管理
│   ├── routers/
│   │   ├── auth.py           # 注册/登录/鉴权
│   │   ├── trading.py        # API配置、策略、交易对、持仓、日志
│   │   ├── stats.py          # 盈利统计
│   │   └── backtest.py       # 历史回测
│   └── services/
│       ├── engine.py         # 交易引擎（核心逻辑）
│       ├── okx_client.py     # OKX ccxt 封装
│       ├── okx_ws_scanner.py # WebSocket RSI 实时扫描
│       └── rsi_calculator.py # Wilder RSI 实现
├── static/
│   ├── index.html            # 仪表板（持仓列表）
│   ├── rsi-scanner.html      # RSI 实时扫描
│   ├── trades.html           # 交易记录
│   ├── stats.html            # 盈利统计
│   ├── backtest.html         # 历史回测
│   ├── settings.html         # 配置页面
│   └── login.html            # 登录
├── docs/                     # 本文档目录
├── run.py                    # 启动脚本
└── requirements.txt
```
