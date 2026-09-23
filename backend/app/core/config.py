"""应用配置：统一从 .env 读取，并做类型校验与启动前的安全检查。

为什么要单独一个文件？
    .env 里的值都是字符串，直接读容易出错（比如 "false" 被当成真值）。
    通过 pydantic-settings 定义成强类型字段后，读取时会自动转换与校验，
    写错格式会在启动时就报错，而不是运行到一半才出问题。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（本文件位于 backend/app/core/config.py，向上三层）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全部配置项。字段名与 .env 中的变量名对应（不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env 里多出的变量不报错，方便临时加调试项
    )

    # ==================== 应用 ====================
    app_name: str = "小家智膳后端"
    app_env: str = "dev"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # ==================== 数据库 ====================
    # 连接串示例：postgresql+psycopg://用户:密码@127.0.0.1:5432/family_menu
    database_url: str
    database_echo: bool = False

    # ==================== 登录令牌 ====================
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 默认 7 天

    # ==================== 微信小程序 ====================
    wx_appid: str = ""
    wx_secret: str = ""

    # ==================== 鉴权开关 ====================
    auth_dev_mode: bool = False
    auth_dev_openid: str = "dev_openid_0001"

    # ==================== 家庭组额度 ====================
    # 一个人最多能拥有几个家庭组（"我创建的"）／最多能加入几个（"我加入的"）。
    #
    # 为什么放在配置里、而不是写死在业务代码里？
    #   因为这两个数会变——用户已经说了以后要开会员，会员加次数。
    #   放配置里改一次 .env 就生效；将来接会员时，只需改
    #   app/services/space_quota.py 里那一个函数，业务代码完全不动。
    max_owned_spaces: int = 2
    max_joined_spaces: int = 2

    # ==================== 收藏分区额度 ====================
    # 一个人最多能建几个**自定义**收藏分区。
    # 默认收藏夹不占额度——它不是一行数据，是 partition_id 为 NULL 的状态。
    # 放配置的原因和家庭组额度一样：将来会员可能加次数，只改 space_quota 那个函数。
    max_favorite_partitions: int = 5

    # ==================== 图片上传 ====================
    # 图片存放目录。相对 backend/ 运行目录（与代码同盘，便于本地开发与备份）。
    # 存本地文件而不是对象存储，是第一版的取舍：换云存储时只动 UploadService 一个类。
    upload_dir: str = "uploads"
    # 单张图片的大小上限（字节）。默认 5MB——手机随手拍足够，再大就该压缩了
    max_upload_bytes: int = 5 * 1024 * 1024

    # ==================== 多模态识别（拍照识别热量） ====================
    # DashScope（通义千问 VL）的 OpenAI 兼容接口。
    # 留空时识别走占位数据（前端提示"演示数据"），不影响其它功能；
    # 把可用 Key 写进 backend/.env 即自动接通真实模型。
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # ⚠️ 默认值只是占位：实现时请核对 DashScope 当前在售的 VL 模型 id
    vision_model: str = "qwen-vl-max"
    # AI 对话用的**文本**模型（不是 VL）。与上面共用 key 和 base_url。
    # 2026-09 实测在售：qwen-plus / qwen-max / qwen-turbo / qwen-flash / qwen3.7-plus 等。
    # 原默认 qwen-plus（够聪明又便宜），2026-09-23 因 qwen-plus 额度耗尽改为 qwen3.7-plus。
    # ⚠️ **这一行只是兜底默认值**。真正生效的是 .env 的 `CHAT_MODEL`；
    #    换模型只改 .env 那一行 + 重启后端，**运行时代码（含本默认值）一律不碰**。
    chat_model: str = "qwen3.7-plus"
    # 对话模型的接入点与密钥：**缺省回落到上面 DashScope 的共用值**。
    # 拆出来的目的：将来"对话走本地模型、识图继续走云"——把 CHAT_BASE_URL / CHAT_API_KEY
    # 指到本地 OpenAI 兼容服务（Ollama / vLLM 等）即可，识图的配置一行不用动。
    # 本地服务通常不需要真 key，随便填个非空字符串（如 "ollama"）就能通过下面的空值检查。
    chat_base_url: str = ""
    chat_api_key: str = ""
    # 对话模型的采样温度。
    # ⚠️ 为什么做成配置而不是像以前那样硬编码 0？
    #   因为不同模型对温度的要求不一样：qwen 系列做"抽结构化字段"这类活，
    #   0 最稳；而 DeepSeek 官方建议非思考模式用 0.0~0.3、
    #   思考模式推荐 0.6（且思考模式下 temperature 实际不生效）。
    #   将来把 CHAT_MODEL 换成 deepseek-flash 时，改这一行就行，不用动代码。
    chat_temperature: float = 0.0

    # ==================== Redis（缓存 + 计数） ====================
    # 本机 Redis 是**原生安装**（E:\Apps\Redis-8.4.6-Windows-x64-...），
    # 以 Windows 服务方式常驻，跑在 6379，不是 Docker 里那个。
    #
    # ⚠️ 别搞混：本机 Docker 里还有一个 `docker-redis-1`，那是 **Dify 的**，
    #    而且它没有映射到宿主端口（`docker ps` 显示的 Ports 是裸的 6379/tcp）。
    #    连通的是哪个用 `redis-cli PING` 确认——能通的就是原生这个。
    #
    # 两个用途（都是 Redis 最经典的用法）：
    #   1) 热点缓存——食物营养查询结果，避免重复走 MCP 子进程
    #   2) 计数器——AI 每日调用配额（INCR + EXPIRE，天然支持次日自动重置）
    redis_url: str = "redis://127.0.0.1:6379/0"
    # 关掉 Redis 时，缓存和配额都退化成"不生效"（功能照常，只是没有加速和限流）。
    # 为什么给开关？本地开发可能懒得开 Redis，不能因为没开就起不来。
    redis_enabled: bool = True

    # ==================== MCP（Model Context Protocol） ====================
    # ⚠️ **默认关闭**。这是刻意的最小风险设计：
    #    MCP 是外部依赖（要 npx、要下包、可能是第三方服务），
    #    它不该成为"起不来后端"的原因，也不该在没准备好的时候改变线上行为。
    #    打开它 = 热量从"大模型估的"变成"查中国食物成分表的"。
    mcp_enabled: bool = False
    # 单次 MCP 工具调用的超时（秒）。
    # 给到 15 秒是因为 `npx -y cn-food-mcp` **首次运行要下载包**，
    # 冷启动可能超过 10 秒；之后有 npx 缓存，正常响应在 1 秒内。
    mcp_call_timeout: float = 15.0

    # ==================== AI 调用配额 ====================
    # 每个用户每天最多能调多少次对话模型。
    # 为什么要有？对话模型按 token 计费，AI 页面是唯一"用户每按一次都可能花钱"的入口。
    # 50 次是给正常使用留足余量（一天记三顿饭也用不了 10 次），
    # 但能挡住"脚本刷接口"这种把额度跑光的情况。
    # 放配置里的原因和家庭组额度一样：将来会员加次数，只改 ai_quota.py 那一个函数。
    max_ai_calls_per_day: int = 50
    # 配额开关。关掉就不计数不限流（调试时方便）。
    ai_quota_enabled: bool = True

    # ==================== 派生属性 ====================
    @property
    def chat_base_url_effective(self) -> str:
        """对话模型实际使用的接入点：独立配置优先，否则回落 DashScope 共用值。"""
        return self.chat_base_url or self.dashscope_base_url

    @property
    def chat_api_key_effective(self) -> str:
        """对话模型实际使用的密钥：独立配置优先，否则回落 DashScope 共用值。"""
        return self.chat_api_key or self.dashscope_api_key

    @property
    def is_prod(self) -> bool:
        """是否生产环境。"""
        return self.app_env.lower() == "prod"

    # ==================== 校验 ====================
    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, value: str) -> str:
        """令牌密钥必须足够长，且不能还是模板里的占位值。"""
        if not value or value.startswith("请替换"):
            raise ValueError("JWT_SECRET 未配置，请先生成随机密钥写入 .env")
        if len(value) < 32:
            raise ValueError("JWT_SECRET 长度不足 32 位，容易被暴力破解")
        return value

    @model_validator(mode="after")
    def _guard_production(self) -> "Settings":
        """生产环境禁止开启开发模式，也不允许缺少微信密钥。"""
        if self.is_prod:
            if self.auth_dev_mode:
                raise ValueError("生产环境（APP_ENV=prod）禁止开启 AUTH_DEV_MODE")
            if not self.wx_secret:
                raise ValueError("生产环境必须配置 WX_SECRET，否则无法登录")
        return self


@lru_cache
def get_settings() -> Settings:
    """读取配置并缓存，避免每次请求都重新解析 .env 文件。"""
    return Settings()


settings = get_settings()
