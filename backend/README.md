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
└─ main.py         应用入口
alembic/           数据库迁移脚本
tests/             自动化测试
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
