# 小家智膳 · 后端服务

家庭菜单与个人生活工作台的 Python 后端。技术栈：**FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic**。

## 快速启动

```bash
# 1. 激活虚拟环境（Windows）
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制配置模板并填写真实值
copy .env.example .env

# 4. 执行数据库迁移（建表）
alembic upgrade head

# 5. 启动服务
python run.py
```

启动后访问 <http://127.0.0.1:8300/docs> 可以看到自动生成的接口文档，并直接在页面上试调。
手机真机调试时改成 `http://<电脑局域网IP>:8300/docs`。

> **端口为什么是 8300 不是 8000？**
> HBuilderX 跑真机调试时会占用 8000 和 8001（它自己的内置服务）。后端占不到 8000 就起不来，
> 而手机连 8000 拿到的是 HBuilderX 返回的纯文本 404，前端报「服务端返回格式异常」——
> 报错完全指不到真正原因。换到 8300 与它隔开，谁先启动都不冲突。
> ⚠️ 改端口要同时改三处：本文件、`run.py`、前端 `uniapp-family-menu/src/services/http.ts`。
> （另有一份本机专用的 `backend/启动后端.bat`，按根目录 `.gitignore` 不入库，改端口时也别忘了它。）

> **为什么用 `python run.py` 而不是直接敲 `uvicorn`？**
> 因为 Windows 上必须额外指定事件循环，直接敲 uvicorn 会报
> `Psycopg cannot use the 'ProactorEventLoop' to run in async mode`。
> 这个参数已经固化在 `run.py` 里，见下面的「Windows 注意事项」。

## Windows 注意事项

本项目用 psycopg 做 PostgreSQL 的**异步**驱动，而它在 Windows 上不能配合
默认的 ProactorEventLoop 使用，必须换成 SelectorEventLoop。

| 场景 | 处理方式 |
| --- | --- |
| 启动服务 | 用 `python run.py`（内部已指定 `--loop app.core.event_loop:selector_loop_factory`） |
| 跑测试 | `tests/conftest.py` 顶部已自动切换事件循环策略，直接 `pytest` 即可 |
| 部署到 Linux | 无需任何处理，Linux 默认就是 SelectorEventLoop |

另外两个和中文 Windows 相关的细节：

- `alembic.ini` **必须保持纯 ASCII**（注释也不例外）。Alembic 用系统区域编码读取该文件，
  中文 Windows 下是 GBK，写入中文注释会直接导致 `UnicodeDecodeError`。
- Python 源码、迁移脚本统一用 **UTF-8 无 BOM**，中文注释才能正常显示。

## 目录结构

```
app/
├─ api/            接口层：收参数、调业务、返回结果
│  ├─ deps.py      公共依赖：数据库会话、当前登录用户
│  └─ v1/          接口 v1 版本
├─ core/           基础设施
│  ├─ config.py    配置读取与安全校验
│  ├─ database.py  数据库连接与会话
│  ├─ security.py  令牌签发与校验
│  ├─ response.py  统一返回格式
│  └─ exceptions.py 业务异常与全局异常处理
├─ models/         数据表定义
├─ schemas/        请求与响应的数据结构
├─ repositories/   数据访问：只负责查/存
├─ services/       业务规则
├─ mcp/            MCP 集成（Model Context Protocol）
│  ├─ servers.py   外部 MCP Server 的注册表
│  ├─ gateway.py   MCP **客户端**：连外部 Server 拿数据
│  └─ server/      MCP **服务端**：把本项目能力暴露给外部 AI 客户端
│     ├─ tools.py  工具实现（4 个只读工具）
│     └─ server.py 协议层：声明工具、分发调用
└─ main.py         应用入口
alembic/           数据库迁移脚本
tests/             自动化测试
tools/             开发辅助脚本（不进运行时）
run.py             开发启动（FastAPI，带热重载）
run_mcp_server.py  MCP Server 启动入口（stdio，由 AI 客户端拉起）
```

分层调用方向是单向的：`api → services → repositories → 数据库`。
反向调用（比如 repositories 去调 services）会让依赖关系混乱，属于禁忌。

## 接口一览（v1）

| 方法 | 路径 | 说明 | 是否需要登录 |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | 健康检查（含数据库连通性） | 否 |
| POST | `/api/v1/auth/login` | 微信登录，返回访问令牌 | 否 |
| GET | `/api/v1/users/me` | 获取当前登录用户 | 是 |

统一返回格式：

```json
{ "code": 0, "message": "success", "data": { } }
```

`code = 0` 表示成功。失败时 `code` 非 0，同时 HTTP 状态码保持语义化。

## 配置说明（.env）

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | 数据库连接串，格式 `postgresql+psycopg://用户:密码@主机:端口/库名` |
| `JWT_SECRET` | 令牌签名密钥，**泄露等于任何人都能伪造登录**，绝不入库 |
| `JWT_EXPIRE_MINUTES` | 令牌有效期，默认 10080（7 天） |
| `WX_APPID` / `WX_SECRET` | 小程序的 AppID 与 AppSecret，AppSecret 只能放后端 |
| `AUTH_DEV_MODE` | 开发模式：跳过微信校验直连登录，**默认关闭，生产禁止开启** |
| `REDIS_URL` / `REDIS_ENABLED` | Redis 连接串与开关。用于营养数据缓存 + AI 调用计数 |
| `MCP_ENABLED` | 是否接入外部 MCP Server 查权威营养数据，**默认关闭** |
| `MCP_CALL_TIMEOUT` | 单次 MCP 工具调用超时（秒），默认 15 |
| `MAX_AI_CALLS_PER_DAY` | 每用户每日 AI 对话上限，默认 50 |
| `CHAT_MODEL` / `CHAT_BASE_URL` / `CHAT_API_KEY` | 对话模型配置；后两项留空时自动沿用 `DASHSCOPE_*` |

`.env` 已在 `.gitignore` 中，不会被提交。新增配置项时请同步更新 `.env.example`。

## 数据库迁移

改表结构的正确姿势是：改 `models/` 里的定义 → 生成迁移 → 执行。
**不要手工去数据库里改表**，否则代码和数据库会对不上，换台机器就跑不起来。

```bash
# 生成迁移脚本（会自动对比模型与数据库的差异）
alembic revision --autogenerate -m "描述本次改动"

# 执行迁移
alembic upgrade head

# 回滚上一个版本
alembic downgrade -1
```

生成的迁移脚本**务必打开看一遍**再执行：自动生成的结果偶尔会有偏差（比如漏掉索引）。

## 测试

```bash
pytest -v
```

测试使用 `.env` 里配置的开发数据库，会产生少量测试数据。

## MCP 集成（Model Context Protocol）

MCP 让 AI 用统一协议去调外部能力。本项目**两个方向都做了**——这样才说得清"什么时候该用、什么时候不该用"。

### ① 客户端：连外部 MCP Server 拿权威数据

**解决的问题**：用户问"这碗红烧肉多少热量"，之前完全靠大模型凭常识估，
同一个问题问三次可能给三个数。现在改成**先查、再算**。

**接的是什么**：`cn-food-mcp`（《中国食物成分表》，1700+ 种食物 × 25 项营养素）
选择理由：中文食物名（USDA 那几个搜不到"排骨""五花肉"）、数据内置在 npm 包里
（不实时请求外部 API）、零 API Key、MIT 协议。

**两级策略**（`services/nutrition_service.py`）：

| 级别 | 触发条件 | 返回的 `source` | 含义 |
| --- | --- | --- | --- |
| 精确 | MCP 查到对应食材 | `mcp_exact` | 直接用查出来的数值 |
| 修正 | MCP 查到主料，但菜是复合菜 | `mcp_derived` | 以主料数值为基准，由模型按烹饪方式修正 |
| 估算 | MCP 不可用 / 没查到 | `llm_estimate` | 纯模型估算 |

⚠️ **关键设计**：成分表是**食材**表，不含"红烧肉""土豆炖牛肉"这类成品菜。
所以查不到是常态而非故障，必须能优雅退化——`source` 字段就是给前端/用户看的可信度标记。

**为什么默认关闭**（`MCP_ENABLED=false`）：首次 `npx -y` 要下载几十 MB，且不是所有环境都有 Node。
关闭时行为**和接入前完全一致**，所以默认关是安全的。想启用：确保 `npx --version` 能跑，再把开关打开。

**自查脚本**：

```bash
./.venv/Scripts/python.exe -m tools.check_mcp_server
```

### ② 服务端：把本项目能力暴露给外部 AI 客户端

把「查冰箱 / 查菜单」按 MCP 协议开放出去，Claude Desktop、Cursor 这类客户端就能直接读本项目的真实数据。

**4 个只读工具**：

| 工具 | 用途 | 权限 |
| --- | --- | --- |
| `list_fridge_items` | 查冰箱食材（可按分类/存放/关键词筛） | 家庭成员 |
| `get_expiring_items` | 查临期/已过期食材，按紧急度排序 | 家庭成员 |
| `list_recipes` | 查菜单里的菜谱 | 家庭成员 |
| `list_categories` | 查菜单分类及每类菜数 | 家庭成员 |

**接入 Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "family-menu": {
      "command": "E:\\AI\\menu\\backend\\.venv\\Scripts\\python.exe",
      "args": ["E:\\AI\\menu\\backend\\run_mcp_server.py"]
    }
  }
}
```

**鉴权**：复用 App 那套 JWT。用户在 App 里登录，把 token 作为工具参数传给 AI 客户端即可。
权限走**同一套** `SpaceService.ensure_member`，App 里看不到的数据这里同样看不到。

**几个刻意的取舍**：

- **全部只读**。写操作经 AI 转述会丢上下文（"把快过期的清掉"——清哪个？），
  出错是不可逆的数据丢失。只读最坏是"查错了"，用户一眼能看出来。
- **不走 HTTP/SSE，只走 stdio**。不需要开端口、不需要备案，
  且 Server 是客户端起的子进程，客户端一停就跟着停，不会有孤儿进程。
- **错误不抛到协议层**。工具失败返回 `{"ok": false, "error": "..."}`，
  模型能读懂原因并转述（"你不是这个家庭组的成员"）；
  抛协议异常的话客户端只会显示"工具执行失败"，信息全丢了。

⚠️ **两个必须知道的坑**（都在代码注释里写明了原因）：

1. **stdout 是 JSON-RPC 通道，绝对不能 `print()`**。混进去一行普通文本，
   客户端解析失败直接断连，而且报错信息很含糊。**日志一律走 stderr。**
2. **Windows 的 stdio 默认是 GBK**。协议规定 UTF-8，所以入口处强制
   `sys.stdout.reconfigure(encoding="utf-8")`，给子进程也带 `PYTHONIOENCODING=utf-8`。
   不改的话中文菜名会乱码或解码失败。

### ③ 什么时候**不该**用 MCP

查自己库里的菜单，直接调 service 就是最优解——套一层 MCP 只增加延迟和故障点。
**判断标准**：这个能力是不是来自项目之外、且未来可能被替换。
食材营养数据符合（在项目之外、将来可能换数据源），所以才值得抽象；
自己家的数据库不符合。
