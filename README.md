# NoteTaker · 智能笔记应用

> 用自然语言记录，AI 自动整理成结构化笔记。自托管、中英双语、双模式权限。
>
> *Describe it in plain language — the AI turns it into a structured note.*

**在线访问：<https://notes.dabuw.online>**

---

## 目录

- [项目简介](#项目简介)
- [功能特性](#功能特性)
- [权限模型](#权限模型)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [本地开发](#本地开发)
- [配置项](#配置项)
- [测试](#测试)
- [部署](#部署)
- [设计取舍](#设计取舍)
- [License](#license)

---

## 项目简介

NoteTaker 是一个**自托管的个人笔记应用**。它的核心想法是：记笔记时不该被表单结构打断思路。

你只需要用日常语言写下「下周三上午 10 点和导师讨论毕业论文选题」，后端会调用大模型把这句话解析成一条结构化笔记 —— 标题、正文、标签，以及**被自动识别出来的事件日期与时间**（`2026-10-21` / `10:00`）。

项目从本地开发一路做到线上运行，完整覆盖了「开发 → 容器化 → 反向代理 → HTTPS → 权限设计 → 备案合规」的全过程，部署在自有云服务器上，不依赖任何 PaaS。

## 功能特性

**笔记管理**

- 笔记的创建、编辑、删除，编辑时 2 秒防抖自动保存
- 按标题与正文实时搜索（前端过滤，无服务端往返）
- 标签云：按使用频次调整字号与颜色深浅，点击标签即可筛选，并显示筛选状态与「清除筛选」
- 事件日期 / 时间：可为笔记附加日程信息

**AI 能力**

- 自然语言 → 结构化笔记（标题 / 正文 / 标签 / 事件时间）
- 中文时间表达解析：今天、明天、后天、大后天、下周三、下午 5 点、晚上 8 点、`5pm`、`20:00`……
- 兼容**任意 OpenAI 兼容接口**（本部署接入 DeepSeek），不绑定特定厂商
- **优雅降级**：AI 不可用时自动退回本地日期时间解析，返回可用草稿 + 黄色警告，而不是报错中断

**界面**

- 中文为默认语言，右上角一键切换英文；选择记入 `localStorage`，也支持 `?lang=en` 直达
- 服务端错误按错误码在前端本地化，英文界面下不会蹦出中文
- 响应式布局，适配桌面与移动端
- 无构建步骤：单个 HTML 文件内含全部 CSS 与 JS，部署即生效

## 权限模型

| | 游客（默认，免登录） | 使用者（输入密码） |
|---|---|---|
| 查看 | 仅标记为公开的笔记 + 自己创建的那条 | 全部 |
| 创建 | 每 IP 最多 `GUEST_NOTE_LIMIT` 条 | 无限 |
| 修改 / 删除 | 仅自己创建的那条 | 全部 |
| 设为公开 | ❌ 强制私密 | ✅ |
| AI 生成 / 翻译 | 每天 `GUEST_AI_DAILY_LIMIT` 次 | 无限 |

两个关键设计：

- **访客创建的内容永远是私密的**，只有创建它的那个 IP 能看到，无法变成公开内容。公开与否只能由登录后的使用者决定。
- **游客也能试用 AI**：`GUEST_AI_DAILY_LIMIT`（默认 5）控制每个 IP 每天的调用次数，用量按天重置；输入密码后不受限制。计数在进程内完成，因此保持 `GUNICORN_WORKERS=1`。
- **`GUEST_NOTE_LIMIT=0` 即只读展示模式**：游客不能创建任何内容，前端也会把「新建笔记」按钮和整个 AI 面板从游客视图中移除（不是置灰，而是不渲染）。用于站点以「非交互式」性质办理备案期间。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 · Flask 3.1 · Flask-SQLAlchemy · SQLAlchemy 2.1 |
| 数据库 | SQLite（WAL 模式） |
| WSGI | gunicorn 26（`gthread`，1 worker × 4 线程） |
| 前端 | 原生 HTML / CSS / JavaScript，无框架、无构建 |
| AI | 任意 OpenAI 兼容 chat-completions 接口（本部署为 DeepSeek） |
| 容器 | Docker · Docker Compose |
| 入口 | 宿主 Nginx 反向代理 + Let's Encrypt（certbot 自动续期） |
| 运行环境 | 腾讯云轻量应用服务器（2 vCPU / 3.6 GB，Ubuntu 24.04） |

## 目录结构

```
.
├── src/
│   ├── main.py               # 应用工厂：配置、蓝图注册、数据库初始化
│   ├── auth.py               # 角色判定、密码校验、可见性查询、登录限流
│   ├── llm.py                # LLM 客户端（SDK 优先 + 纯 HTTP 兜底）
│   ├── call_llm_model.py     # 自然语言 → 结构化字段，含本地解析回退
│   ├── models/
│   │   ├── note.py           # 笔记模型（含 author_ip / is_public）
│   │   └── user.py           # SQLAlchemy 实例
│   ├── routes/
│   │   ├── auth.py           # 登录 / 登出 / 会话状态
│   │   ├── note.py           # 笔记 CRUD、配额、归属与可见性控制
│   │   ├── tags.py           # 标签云统计与按标签筛选
│   │   ├── generate.py       # AI 生成笔记
│   │   ├── translate.py      # 翻译接口（界面切换已取代其 UI，接口保留）
│   │   └── user.py           # 遗留用户接口（已加登录保护）
│   └── static/
│       ├── index.html        # 单文件 SPA（含全部 CSS/JS 与 i18n 表）
│       └── favicon.ico
├── tests/
│   ├── run_all.py            # 统一测试入口
│   ├── test_permissions.py   # 权限模型套件（63 项）
│   └── test_llm_integration.py  # LLM 集成套件（25 项）
├── Dockerfile
├── docker-compose.yml
├── gunicorn.conf.py
├── .env.example              # 全部配置项与说明
├── DEPLOY.md                 # 部署、更新与备份手册
└── requirements.txt
```

## 本地开发

```bash
git clone https://gitcode.com/m0_54185611/my-note-book.git
cd my-note-book

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # 至少填写 SECRET_KEY 与 APP_PASSWORD
python src/main.py          # 默认监听 127.0.0.1:5001
```

打开 <http://127.0.0.1:5001> 即可。首次启动会自动建表。

> `SECRET_KEY` 必须填写且不少于 32 字符，否则应用**拒绝启动** —— 它是会话 Cookie 签名的唯一保护，不允许存在默认值。
> 生成方式：`python3 -c "import secrets; print(secrets.token_hex(32))"`

## 配置项

完整清单与说明见 [`.env.example`](.env.example)，其中需要关注的是：

| 变量 | 作用 |
|---|---|
| `SECRET_KEY` | **必填**，会话签名密钥，弱值会导致启动失败 |
| `APP_PASSWORD` | **必填**，使用者模式的共享密码 |
| `GUEST_NOTE_LIMIT` | 每 IP 游客可创建条数；`0` 表示只读展示模式 |
| `GUEST_AI_DAILY_LIMIT` | 每 IP 游客每天可调用的 AI 次数；`0` 表示游客不可用 AI |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | AI 接口配置，留空则优雅降级 |
| `SESSION_COOKIE_SECURE` | 生产环境保持 `true`（经 HTTPS 提供服务） |
| `SESSION_LIFETIME_DAYS` | 登录态有效期 |

> 旧的 `GITHUB_TOKEN` / `GITHUB_MODEL` / `GITHUB_MODELS_ENDPOINT` 仍作为回退生效。
> **接入非 GitHub 服务商时务必显式设置 `LLM_MODEL`**，否则 GitHub 的默认模型名会被原样发给对方。

## 测试

```bash
python tests/run_all.py
```

两套件都是直接驱动真实 Flask 应用的独立脚本，**不需要额外的测试依赖**（无需 pytest）：

| 套件 | 项数 | 覆盖内容 |
|---|---|---|
| `test_permissions.py` | 63 | 游客配额、跨访客越权（读/改/删）、私密笔记与标签/搜索的泄漏防护、登录与登出、错误密码、暴力破解限流、遗留接口鉴权、**只读模式**、AI 降级行为 |
| `test_llm_integration.py` | 25 | 用内置的假 OpenAI 兼容端点验证真实调用链路：SDK 路径与纯 HTTP 兜底路径、401 提示可读性、端点不可达时的降级、**API Key 不泄漏进错误信息** |

## 部署

采用「宿主 Nginx + Docker 容器」的拓扑，容器端口只绑定回环地址，不额外开放任何公网端口：

```
Internet
   │  云安全组仅放行 22 / 80 / 443
   ▼
宿主 Nginx :443（Let's Encrypt，自动续期）
   │  proxy_pass，并强制下发 X-Real-IP=$remote_addr
   ▼
127.0.0.1:18100          ← 仅回环，公网不可直连
   │
   ▼
Docker 容器（gunicorn + Flask）
   ├── ./data/app.db      SQLite，绑定挂载到宿主，重建镜像不丢数据
   └── 出站 → LLM 接口    API Key 仅存于服务器 .env
```

完整的部署、更新、备份与变更流程见 **[DEPLOY.md](DEPLOY.md)**。

## 设计取舍

几个刻意的选择，以及背后的原因：

**访客身份用 `X-Real-IP` 而不是 `X-Forwarded-For`**
配额必须键在不可伪造的地址上。`X-Forwarded-For` 由 `$proxy_add_x_forwarded_for` **追加**，客户端可以自带前缀来伪造；而 `X-Real-IP` 由 Nginx 用 `$remote_addr` **覆盖**，无法伪造。已实测：伪造不同 IP 的请求仍被同一条配额拦住。

**访客内容强制私密**
这样即使开放游客写入，站点也不会变成「用户发布内容、所有人都能看到」的 UGC 平台，规避了内容审核与实名要求。备案期间进一步把 `GUEST_NOTE_LIMIT` 设为 `0`。

**SQLite 而不是共享 MySQL**
这是单用户笔记应用，不是高并发服务。SQLite 单文件便于备份、零外部依赖、不与服务器上其他项目共用数据库；配合 WAL 模式足以支撑读写。gunicorn 因此刻意只用 1 个 worker + 多线程，避免多进程争抢写锁。

**AI 走 OpenAI 兼容接口而不是绑定某家 SDK**
换服务商只需改三个环境变量。这条路径在两处踩过坑、也因此更稳：`openai` 1.51.2 与 `httpx` 0.28 不兼容会导致所有调用失败，已通过固定 `httpx==0.27.2` 修复；同时客户端实现为「SDK 优先、纯 HTTP 兜底」，即使 SDK 因版本问题不可用，AI 仍能正常工作。

**AI 失败时降级而不是报错**
生成接口在模型不可用时返回 **200 + `ai_used: false` + `warning`**，并用本地规则解析出日期时间，前端以黄色提示条展示。原始实现会返回 500，导致前端把已经算好的回退结果整个丢弃。

**时间戳统一带 `Z` 后缀**
数据库存的是 UTC 朴素时间，浏览器按 ES 规范会把 `2026-10-16T10:16:21` 当作**本地时间**解析。序列化时补上 `Z` 由客户端换算，避免相对日期整体偏移一个时区。

## License

MIT
