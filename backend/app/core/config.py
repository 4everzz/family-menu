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

    # ==================== 派生属性 ====================
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
