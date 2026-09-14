"""登录相关的请求与响应模型。

这里有两套请求模型，规则刻意不一样：
    注册（RegisterRequest）—— 会往库里写数据，所以卡得严：用户名格式、密码长度、
        两次密码是否一致都校验。
    登录（PasswordLoginRequest）——只是拿输入去比对，所以卡得松：
        只限制长度上限防滥用，不套注册那套格式规则。
        原因是"规则会变"：如果哪天把用户名上限从 20 改成 32，
        老账号里 25 位的那个（注册时合法）会连登录都进不去——
        连自己账号都登不了的坑，比什么都难查。

另外注意：注册时**只收账号信息**（用户名 + 密码），不收昵称、头像这些个人资料。
用户想改资料去「我的」页改（见 app/api/v1/users.py 的更新接口）。
理由：注册表单每多一个字段，放弃注册的人就多一分；能省则省。
"""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.password import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.models.user import USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH
from app.schemas.user import UserInfo

# 用户名字符集：只允许 ASCII 字母、数字、下划线。
#
# 为什么账号名不做多语言（不接受中文/日文/emoji）？
#   1. 防同形字冒充：西里尔字母 "а" 和拉丁字母 "a" 长得几乎一模一样，
#      却是两个完全不同的字符。允许非 ASCII 就意味着能造出"看着跟别人一模一样"的账号。
#   2. 输入成本：中文用户名在英文输入法下、在别人手机上，几乎没法准确输入。
#   3. 前后端一致性：ASCII 没有全角/半角、编码归一化这些坑。
# 注意：**昵称**不受这个限制——中文、emoji 都随便用，昵称本来就是给人看的。
#      也就是说，登录用用户名（严格），展示用昵称（自由），两件事分开。
USERNAME_RE = re.compile(
    rf"[A-Za-z0-9_]{{{USERNAME_MIN_LENGTH},{USERNAME_MAX_LENGTH}}}"
)

USERNAME_FORMAT_MESSAGE = (
    f"用户名需为 {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} 位字母、数字或下划线"
)


def _strip_lower(value: object) -> object:
    """用户名归一化：去掉首尾空格并统一转小写。

    注册和登录必须用同一套：注册时把 "Tom" 存成 "tom"，
    登录时也必须把 "Tom" 转成 "tom" 再查，
    否则用户明明注册成功了，却因为当初输入法首字母大写而登不进来。
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _strip(value: object) -> object:
    """密码归一化：去掉首尾空格。

    为什么密码也要去空格？
        手机输入法和复制粘贴很容易在末尾带一个看不见的空格。
        如果不去掉，用户注册时的密码和登录时输入的就会差一个空格，
        表现出来就是"密码明明是对的，却一直提示错误"——这种问题极难自查。
        代价是密码不能以空格开头或结尾，对这个场景完全可以接受。
    """
    if isinstance(value, str):
        return value.strip()
    return value


class _UsernameFieldMixin(BaseModel):
    """把"用户名归一化"抽出来，注册和登录共用同一套。"""

    @field_validator("username", mode="before", check_fields=False)
    @classmethod
    def _normalize_username(cls, value: object) -> object:
        return _strip_lower(value)


class _PasswordFieldMixin(BaseModel):
    """密码归一化：同样地，注册和登录必须一致。"""

    @field_validator("password", mode="before", check_fields=False)
    @classmethod
    def _normalize_password(cls, value: object) -> object:
        return _strip(value)


class RegisterRequest(_UsernameFieldMixin, _PasswordFieldMixin):
    """注册请求。

    ⚠️ 这里只有账号本身的信息（用户名 + 密码 + 确认密码），**没有昵称、头像**。
       个人资料一律在登录之后、去「我的」页修改。
    """

    username: str = Field(
        ...,
        description=f"登录用户名，{USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} 位字母、数字或下划线",
    )
    password: str = Field(
        ...,
        description=f"密码，{PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 位",
    )
    password_confirm: str = Field(
        default="",
        description="再输一遍密码，用于确认没打错。服务端会比对两者是否一致",
    )

    # 注意这几个字段都刻意**没有**用 min_length 约束：
    # Pydantic 内置约束报的是英文（"String should have at least 1 character"），
    # 而这些消息会原样显示给用户。空值交给下面的自定义校验器处理，
    # 这样每一种情况都能给出一句中文说明。
    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        """用户名格式校验。"""
        if not value:
            raise ValueError("请填写用户名")
        if not USERNAME_RE.fullmatch(value):
            raise ValueError(USERNAME_FORMAT_MESSAGE)
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        """密码长度校验。"""
        if len(value) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"密码至少 {PASSWORD_MIN_LENGTH} 位")
        if len(value) > PASSWORD_MAX_LENGTH:
            raise ValueError(f"密码最多 {PASSWORD_MAX_LENGTH} 位")
        return value

    @field_validator("password_confirm", mode="before")
    @classmethod
    def _normalize_password_confirm(cls, value: object) -> object:
        """确认密码走和密码一样的归一化，否则"两边都去了空格"这个前提就不成立了。"""
        return _strip(value)

    @model_validator(mode="after")
    def _cross_field_checks(self) -> "RegisterRequest":
        """跨字段校验。

        为什么要服务端再比一次、而不是只靠前端？
            前端那个确认框是为了"让用户当场发现自己打错了"，属于体验；
            但接口是公开的，别人可以绕过界面直接调。服务端比一次，
            才能保证库里存下来的账号一定是"两次输入一致"的。

        为什么"没填确认密码"也放在这里查、而不写成独立的字段校验器？
            password_confirm 带默认值 ""，而 Pydantic **默认不会对"用了默认值"的字段
            运行校验器**，所以独立的字段校验器在"字段缺失"时压根不会触发，
            提示会变成含糊的"两次输入的密码不一致"。放在这里统一判断，
            少一个校验器，提示也更准确。
        """
        if not self.password_confirm:
            raise ValueError("请再输入一次密码")

        # 打错两次是最常见的情况，优先提示它
        if self.password != self.password_confirm:
            raise ValueError("两次输入的密码不一致")

        # 再查弱密码：用户名 zhangsan、密码也填 zhangsan，这种账号在撞库时最先失守
        if self.password == self.username:
            raise ValueError("密码不能与用户名相同")

        return self


class PasswordLoginRequest(_UsernameFieldMixin, _PasswordFieldMixin):
    """用户名 + 密码登录请求。

    注意这里**不**做格式校验，只限制长度上限：
    格式规则属于"注册时该满足的条件"，登录时只要原样拿去比对即可。
    见本文件开头的说明。
    """

    username: str = Field(..., max_length=64, description="登录用户名")
    password: str = Field(..., max_length=128, description="密码")

    # 只挡"什么都没填"（否则会拿空字符串去查库，白跑一次）；
    # 格式与长度下限一概不管，见本文件开头关于"登录规则要宽松"的说明。
    @field_validator("username")
    @classmethod
    def _require_username(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写用户名")
        return value

    @field_validator("password")
    @classmethod
    def _require_password(cls, value: str) -> str:
        if not value:
            raise ValueError("请填写密码")
        return value


class WechatLoginRequest(BaseModel):
    """微信小程序登录请求。"""

    code: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="小程序 uni.login() 返回的临时登录凭证，只能用一次且 5 分钟内有效",
    )


class LoginResponse(BaseModel):
    """登录/注册成功后的响应。"""

    token: str = Field(..., description="访问令牌，后续请求放在请求头 Authorization: Bearer <令牌>")
    token_type: str = Field(default="Bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期（秒）")
    user: UserInfo = Field(..., description="用户信息")
