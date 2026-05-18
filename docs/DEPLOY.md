# 🚀 部署到云服务器

完整上线 = **服务器** + **域名** + **Cloudflare Tunnel** + **Cloudflare Access**(免费邮箱验证登录)。
全程不需要公网 IP、不需要折腾 SSL,Cloudflare 自动帮你搞定。

---

## 一、买服务器 + 域名

### 服务器
**阿里云轻量·新加坡 2核2G 50G 3M** ¥70/月
🔗 https://www.aliyun.com/product/swas
- 地域:**必选新加坡或香港**
- 镜像:**Ubuntu 22.04**

### 域名
**阿里云万网**,`.top` 首年 ¥9
🔗 https://wanwang.aliyun.com/domain/
- 国内域名需实名(1-2 天)
- 或用 **Cloudflare Registrar** 免实名(需信用卡,`.com` $10.44)

---

## 二、服务器初始化

SSH 登录后:

```bash
# 1. 更新系统
apt update && apt upgrade -y

# 2. 装 Docker
curl -fsSL https://get.docker.com | bash
systemctl enable --now docker

# 3. 创建项目目录
mkdir -p /opt/stockwatch && cd /opt/stockwatch

# 4. 拉代码
git clone https://github.com/pig007aklg-pigdevelop/stockwatch.git .

# 5. 配置环境变量
cp .env.example .env
nano .env   # 填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

---

## 三、装 FutuOpenD(富途网关)

⚠️ 富途官方 **不提供 Docker 镜像**,需在宿主机安装。

```bash
# 下载 Linux 版 FutuOpenD
cd /opt
wget https://softwarefile.futunn.com/soft/openAPI/FutuOpenD_Linux_x64.tar.gz
tar -xzf FutuOpenD_Linux_x64.tar.gz
cd FutuOpenD_*

# 编辑配置(填富途账号)
nano FutuOpenD.xml
# 至少修改:
#   <login_account>你的富途账号</login_account>
#   <login_pwd_md5>密码的MD5</login_pwd_md5>  (用 echo -n 'pass' | md5sum)

# 后台启动
nohup ./FutuOpenD > futu.log 2>&1 &

# 验证端口
ss -tlnp | grep 11111
```

> 📱 启动后,手机富途 App 会收到 **OpenAPI 登录请求**,点击同意。

---

## 四、启动应用

```bash
cd /opt/stockwatch
docker compose up -d
docker compose logs -f
```

浏览器访问:`http://你服务器公网IP:8080` 应该能看到看板。

---

## 五、绑定域名 + Cloudflare Tunnel(免费 HTTPS)

### 5.1 域名托管到 Cloudflare(免费)
1. https://dash.cloudflare.com 注册
2. **Add site** → 输入你的域名(如 `stockwatch.top`)
3. Cloudflare 给你 2 个 NS,**回阿里云域名管理把 DNS 服务器改成它们**
4. 等 5-30 分钟生效

### 5.2 创建 Tunnel
在 Cloudflare 控制台:
1. **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel**
2. 选 **Cloudflared**,起个名字 `stockwatch`
3. 复制安装命令(类似):
   ```bash
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cf.deb
   dpkg -i cf.deb
   cloudflared service install eyJxxx...
   ```
4. 在服务器执行,Tunnel 状态变绿
5. **Public Hostname** 添加:
   - Subdomain: `app`
   - Domain: `stockwatch.top`
   - Service: `http://localhost:8080`

现在访问 **https://app.stockwatch.top** 就能直接进看板 ✅(免费 HTTPS,无需公网 IP)

---

## 六、Cloudflare Access(邮箱验证登录)

防止陌生人访问你的看板:

1. **Zero Trust** → **Access** → **Applications** → **Add an application**
2. 选 **Self-hosted**
3. Application name: `StockWatch`
4. Session Duration: **24 hours**
5. Application domain: `app.stockwatch.top`
6. Next → **Add a policy**:
   - Policy name: `Only Me`
   - Action: **Allow**
   - Include → **Emails** → 填你自己的邮箱
7. Next → Save

现在再访问 `https://app.stockwatch.top`:
- 会跳转 Cloudflare 登录页
- 输邮箱 → 收 6 位验证码 → 验证 → 进看板
- 24 小时内免重复登录

---

## 七、运维

### 查看日志
```bash
docker compose logs -f --tail 100
tail -f /opt/FutuOpenD_*/futu.log
```

### 重启
```bash
docker compose restart
```

### 备份数据库
```bash
# 简单 cron 备份
echo "0 3 * * * cp /opt/stockwatch/data/stockwatch.db /opt/stockwatch/data/backup-\$(date +\%F).db" | crontab -
```

### 更新代码
```bash
cd /opt/stockwatch
git pull
docker compose build && docker compose up -d
```

---

## 八、常见问题

### Q: FutuOpenD 启动失败
- 检查富途账号已开通 OpenAPI(本地登录富途牛牛 PC 版,设置 → 接口)
- 检查 `FutuOpenD.xml` 账号密码 MD5 正确
- 手机富途未授权 → 重启 FutuOpenD 等推送

### Q: 看板能打开但价格一直空
- `docker compose logs app` 看是否连上 FutuOpenD
- 容器里 `host.docker.internal:11111` 能否 telnet 通
- 富途账号在交易时段才有实时行情

### Q: Telegram 收不到推送
- `.env` 里 TG_TOKEN 和 CHAT_ID 是否正确
- 容器是否能访问 api.telegram.org(新加坡节点没问题,香港节点可能要代理)

### Q: 安全性?
- Cloudflare Access 已经防住外部访问
- `.env` 已被 `.gitignore` 排除,不会推到 GitHub
- 服务器开 ufw 防火墙只放 22/443:
  ```bash
  ufw allow 22 && ufw allow 443 && ufw --force enable
  ```
- 不需要开 8080 给公网(Tunnel 走内部)
