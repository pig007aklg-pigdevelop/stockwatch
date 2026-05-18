# 📈 StockWatch · Phase 1（后端核心）

美股 + 港股盯盘系统，第一阶段交付：富途实时价格 + 定时扫描 + 止盈止损 Telegram 推送。

> Phase 2 将加入 NiceGUI 看板和 Cloudflare Access 部署。

---

## 🎯 Phase 1 功能

- ✅ SQLite 数据库（持仓 / 价格快照 / 信号日志）
- ✅ 富途 OpenAPI 实时拉港股+美股价格
- ✅ APScheduler 每 15 分钟定时扫描（仅交易时段）
- ✅ 整点摘要 + 触及止盈止损立即推送 Telegram
- ✅ Docker Compose 一键启动（含 FutuOpenD 网关）
- ⏳ Web 看板（Phase 2）
- ⏳ 新闻聚合 + LLM 摘要（Phase 2）

---

## 🚀 本地快速测试（不用买服务器）

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 准备 FutuOpenD 网关
富途 OpenAPI 必须通过本地网关运行：
- Mac/Win 下载：https://www.futunn.com/download/openAPI
- 装好后启动 FutuOpenD，登录富途账号（手机会收到授权请求）
- 默认端口 11111

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 填入 Telegram Bot Token 和 Chat ID
```

### 4. 初始化数据库 + 录入持仓
```bash
python -m app.db.init_db
python scripts/add_position.py NVDA US 135.0 10  # 代码 市场 成本价 数量
python scripts/add_position.py 00700 HK 380.0 100
```

### 5. 启动
```bash
python -m app.main
```

---

## 🐳 Docker 部署（Phase 2 完善后使用）

```bash
docker compose up -d
```

---

## 📁 目录结构

```
stockwatch/
├── README.md
├── requirements.txt
├── .env.example
├── docker-compose.yml          # Phase 2
├── Dockerfile                  # Phase 2
├── app/
│   ├── main.py                 # 入口
│   ├── config.py               # 配置加载
│   ├── db/
│   │   ├── models.py           # SQLAlchemy 模型
│   │   └── init_db.py
│   ├── jobs/
│   │   ├── scheduler.py        # APScheduler
│   │   ├── price_scanner.py    # 价格扫描
│   │   └── signal_engine.py    # 止盈止损判断
│   └── services/
│       ├── futu_client.py      # 富途封装
│       └── telegram_bot.py     # 推送
└── scripts/
    └── add_position.py         # 命令行加持仓
```

---

## ⚠️ 已知限制

- Phase 1 没有看板，加持仓靠脚本
- 未做异常重试（富途断线后需手动重启）
- 未做多用户/登录
- 港股 Level 1 行情有富途内部刷新频率限制

这些都会在 Phase 2 完善。

---

## 🔧 下次对话告诉我做这些（Phase 2）

- [ ] NiceGUI 看板（增删改持仓 / K线 / 新闻流）
- [ ] 新闻 RSS 聚合 + LLM 摘要
- [ ] Cloudflare Tunnel + Access 部署文档
- [ ] Docker Compose 完整化
- [ ] 异常监控 + 自动重连
