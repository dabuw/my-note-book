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

### 只读展示模式（`GUEST_NOTE_LIMIT=0`）— 当前已启用

设为 `0` 后网站整体降级为**只读展示**，用于备案期间把站点呈现为**非交互式**：

- 后端：游客 `POST /api/notes` 返回 `403` + `code=guest_write_disabled`
- 前端：游客视图里**直接隐藏**「New Note」按钮和整个 AI 面板（不是置灰，是不渲染），
  只留「📖 只读浏览」标识与「🔑 管理员登录」入口
- 游客仍可浏览公开笔记；管理员登录后功能完全不受影响

备案通过后改回 `1` 即可恢复游客写入（改 `.env` 后 `docker compose up -d`，**无需重建镜像**）。

> 判断依据：阿里云官方《公安联网备案信息填写指南》把「**站内搜索**、留言板、在线聊天、用户评论」列为交互式服务特征，
> 「非交互式网站指仅展示静态信息、无用户互动功能的网站」。
> 注意页面顶部的搜索框是**纯前端**过滤（`searchNotes()` 在浏览器内筛已加载的列表，不发服务端请求）。
> 若审核方对「站内搜索」从严认定，可以再把搜索框也对游客隐藏。

## 页脚备案号

页脚在 `src/static/index.html` 的 `<footer class="site-footer">`：

- **ICP 备案号已填入**（`新ICP备2026009541号-1`，链接 beian.miit.gov.cn），静态渲染，不依赖 JS
- **公安联网备案号是隐藏占位**。办理完成后改三处：
  1. 去掉 `<div class="footer-line" id="policeRecord" style="display:none;">` 里的 `style="display:none;"`
  2. 把「新公网安备 XXXXXXXXXXXXXX 号」换成真实备案号
  3. 链接里 `code=` 后补上公安备案查询编号，官方图标放到 `src/static/police-record.png`

改完需 `docker compose up -d --build` 重建镜像（静态文件是打进镜像的）。

## AI 功能配置

AI 生成走**任意 OpenAI 兼容的 chat-completions 接口**。三个变量（旧的 `GITHUB_*` 名字仍作为回退生效）：

> 界面语言切换已取代原来的「翻译」按钮（`src/static/index.html` 里已无翻译 UI 与 `translateCurrentNote()`），
> 但后端 `POST /api/translate`（需登录）与 `src/llm.py::translate()` 仍然保留可用，
> Nginx 的 AI 限流规则也同时覆盖它。如果需要彻底删除，告诉我即可一并清理（涉及 Nginx 配置改动）。

```bash
LLM_BASE_URL=https://api.deepseek.com/v1   # 或 https://models.github.ai/inference
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-xxx                         # 或 ghp_xxx
LLM_TIMEOUT=60
```

⚠️ **接入非 GitHub 服务商时务必显式设置 `LLM_MODEL`。** 老变量 `GITHUB_MODEL` 的默认值是 `openai/gpt-4.1-mini`，如果不设 `LLM_MODEL`，这个 GitHub 的模型名会被原样发给 DeepSeek，导致 404。`.env.example` 已把 `GITHUB_MODEL` 注释掉来规避这个坑。

**没配 API Key 时不会崩**，而是优雅降级：

| 接口 | 行为 |
|---|---|
| `POST /api/generate-notes` | **200** + `ai_used=false` + `warning`，标题/正文/标签由本地逻辑生成，**日期时间仍会被正确解析** |
| `POST /api/translate` | **503** + `code=ai_not_configured`（翻译没有有意义的离线替代，所以明确报错） |

前端对应显示黄色警告条（生成）或明确的未配置提示（翻译），而不是红色报错。

> 依赖提示：`requirements.txt` 里钉了 `httpx==0.27.2`。`openai==1.51.2` 会向 `httpx.Client` 传 `proxies=`，而 httpx 0.28 移除了该参数 —— 不钉版本会报 `Client.__init__() got an unexpected keyword argument 'proxies'`，AI 全挂。另外 `src/llm.py` 是「SDK 优先、纯 HTTP 兜底」双路径，即使 SDK 因版本问题不可用，AI 仍能工作。

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
