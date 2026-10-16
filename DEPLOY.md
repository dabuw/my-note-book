# 部署说明（腾讯云 CVM + Docker + 宿主 Nginx）

## 架构

```
Internet
   │  腾讯云安全组只放行 22 / 80 / 443
   ▼
宿主机 Nginx :443（Let's Encrypt，notes.dabuw.online）
   │  proxy_pass，并强制下发 X-Real-IP=$remote_addr
   ▼
127.0.0.1:18100   ← 仅回环，公网无法直连
   │
   ▼
Docker 容器 notetaker（gunicorn + Flask，容器内 5001）
   ├── ./data/app.db             SQLite，绑定挂载到宿主机，重建镜像不丢数据
   └── 出站 → GitHub Models API  GITHUB_TOKEN 仅存在于服务器 .env
```

## 服务器路径

| 项 | 路径 |
|---|---|
| 代码 | `/opt/my-web/notetaking/` |
| 数据（SQLite） | `/opt/my-web/notetaking/data/app.db` |
| 密钥 | `/opt/my-web/notetaking/.env`（权限 600） |
| Nginx 站点 | `/etc/nginx/sites-available/notes.dabuw.online` |
| Nginx 限流区 | `/etc/nginx/conf.d/notes-ratelimit.conf` |

## 权限模型

| | 游客（默认，免登录） | 使用者（输入密码） |
|---|---|---|
| 查看 | 仅 `is_public=true` 的笔记 + 自己创建的那条 | 全部 |
| 创建 | 每 IP 最多 `GUEST_NOTE_LIMIT`（默认 1）条 | 无限 |
| 修改 / 删除 | 仅自己创建的那条 | 全部 |
| 设为公开 | ❌ 强制为私密 | ✅ |
| AI 生成 / 翻译 | ❌ | ✅ |

要点：

- **游客创建的内容永远是私密的**，不会变成所有访客可见的公开内容。公开与否只能由登录后的使用者决定。
- 识别访客靠 Nginx 下发的 `X-Real-IP`（Nginx 会覆盖客户端传来的同名头，无法伪造）。
  **不要改用 `X-Forwarded-For` 判断配额** —— 该头由 `$proxy_add_x_forwarded_for` 追加，客户端可自行注入前缀绕过限制。
- 游客删除自己的笔记后配额会释放，可以再建一条。因为游客笔记始终私密，这不构成内容滥用风险。

## 部署 / 更新流程

```bash
ssh dabuw

# 首次
sudo mkdir -p /opt/my-web/notetaking
sudo chown ubuntu:ubuntu /opt/my-web/notetaking
git clone https://gitcode.com/m0_54185611/my-note-book.git /opt/my-web/notetaking
cd /opt/my-web/notetaking
cp .env.example .env && chmod 600 .env
# 编辑 .env：填 SECRET_KEY、APP_PASSWORD、GITHUB_TOKEN

# ⚠️ 必须先建好数据目录并交给容器用户（uid 10001）。
# 否则 Docker 会以 root 创建 ./data，容器内非 root 进程无法写入，
# SQLite 会报 "unable to open database file" 启动失败。
mkdir -p data
sudo chown -R 10001:10001 data

docker compose up -d --build

# 日常更新（数据目录已就绪，无需重复 chown）
cd /opt/my-web/notetaking && git pull && docker compose up -d --build
```

生成 `SECRET_KEY`：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 备份

数据就是一个文件，直接拷走即可：

```bash
cp /opt/my-web/notetaking/data/app.db ~/notetaker-$(date +%F).db
```

SQLite 开了 WAL 模式，`.db-wal` 里可能还有未落盘的数据。在线热备份请用 SQLite 自带命令：

```bash
sqlite3 /opt/my-web/notetaking/data/app.db ".backup '/tmp/app-backup.db'"
```

## 安全注意事项

- `.env` 通过 `env_file` 注入，且被 `.dockerignore` 排除，**不会进入镜像层**（镜像层里的 ENV 可用 `docker history` 读出）。
- 密码只存服务器 `.env`，前端 JS 里没有任何密码或 API key。
- `APP_PASSWORD` 是唯一的访问凭据，请使用长随机值；登录接口在 Nginx（`limit_req`）和应用内（每 IP 5 分钟 10 次）双层限流。
- 若服务要直接暴露而不经过 Nginx，必须把 `SESSION_COOKIE_SECURE` 设为 `false` 才能登录，但同时会失去 `X-Real-IP` 的可信来源，**按 IP 配额会退化为按直连地址**，不建议。
