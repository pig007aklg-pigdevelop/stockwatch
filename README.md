# 📈 StockWatch

美股 + 港股盯盘系统:富途实时行情 + 看板 + Telegram 推送 + 新闻聚合。

---

## ✨ 功能

- 📊 **Web 看板**:浏览器增删改持仓、查看实时盈亏
- 🌋 **富途 OpenAPI**:港股 + 美股实时价格
- ⏱ **定时扫描**:交易时段每 15 分钟自动判断止盈止损
- 📢 **Telegram 推送**:触发信号立即推 + 整点摘要
- 📰 **新闻聚合**:Yahoo Finance + Google News,可选 LLM 中文摘要
- 🚨 **信号历史**:所有止盈止损事件可追溯
- 🐳 **Docker 一键部署** + Cloudflare Tunnel 免费 HTTPS

---

## 🚀 本地试跑

```bash
git clone https://github.com/pig007aklg-pigdevelop/stockwatch.git
cd stockwatch

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

cp .env.example .env
# 编辑 .env 填 Telegram Token

# 启动(富途未启动时,价格功能不可用,看板和持仓管理仍可用)
python -m app.main
```

浏览器打开 http://localhost:8080

---

## ☁️ 部署到云服务器

详见 [docs/DEPLOY.md](docs/DEPLOY.md) — 含阿里云 + Cloudflare Tunnel + Access 完整步骤。

---

## 📁 项目结构

```
stockwatch/
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── docs/DEPLOY.md
├── app/
│   ├── main.py                 # 入口
│   ├── config.py
│   ├── ui.py                   # NiceGUI 看板(4 个页面)
│   ├── db/models.py
│   ├── jobs/
│   │   ├── scheduler.py        # APScheduler
│   │   ├── price_scanner.py
│   │   ├── signal_engine.py
│   │   └── news_scraper.py     # RSS 抓新闻
│   └── services/
│       ├── futu_client.py
│       ├── telegram_bot.py
│       └── llm_client.py       # 新闻 LLM 摘要
└── scripts/add_position.py     # CLI 加持仓
```

---

## 🛠 配置说明 (.env)

```
TELEGRAM_BOT_TOKEN=xxx            # @BotFather 拿
TELEGRAM_CHAT_ID=xxx              # @userinfobot 拿
FUTU_HOST=127.0.0.1               # FutuOpenD 地址
FUTU_PORT=11111
SCAN_INTERVAL_MINUTES=15          # 扫描间隔
HOURLY_SUMMARY=true               # 整点是否推摘要
ALERT_COOLDOWN_MINUTES=60         # 同信号冷却,防刷屏
WEB_PORT=8080
OPENAI_API_KEY=                   # 可选,用于新闻摘要
NEWS_INTERVAL_MINUTES=30
```

---

## 🔮 后续可加

- [ ] K 线图(TradingView 嵌入)
- [ ] 分笔交易日志 + 真实持仓回测
- [ ] 多策略引擎(移动止盈/MA 突破等)
- [ ] 周报 PDF 自动生成
- [ ] 移动端 PWA

需要哪个,开新对话告诉我。
