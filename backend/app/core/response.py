"""统一接口返回格式：{ code, message, data }。

为什么要统一格式？
    前端只需要写一套解析逻辑：先看 HTTP 状态码，再看 code。
    如果每个接口返回结构都不一样，前端就得为每个接口写特例，很容易漏。

约定：
    code = 0      成功
    code != 0     业务错误，具体含义见下方错误码表
    HTTP 状态码同时保持语义化（401 未登录、403 无权限、404 不存在、422 参数错、500 服务端错误），
    方便前端用拦截器统一处理"登录过期"这类情况。
"""

from typing import Any

# ==================== 错误码表 ====================
CODE_SUCCESS = 0          # 成功
CODE_BUSINESS = 1000      # 通用业务错误
CODE_UNAUTHORIZED = 1001  # 未登录 / 令牌无效或过期
CODE_PARAM_INVALID = 1002 # 参数校验不通过
CODE_FORBIDDEN = 1003     # 已登录但无权限
CODE_NOT_FOUND = 1004     # 数据不存在
CODE_ACCOUNT_DISABLED = 1005  # 账号被停用
CODE_WX_NOT_CONFIGURED = 1006  # 服务端未配置微信密钥
CODE_WX_UNAVAILABLE = 1007     # 微信服务不可用
CODE_WX_LOGIN_FAILED = 1008    # 微信返回登录失败
CODE_USERNAME_TAKEN = 1009     # 用户名已被占用
CODE_BAD_CREDENTIALS = 1010    # 用户名或密码不正确（故意不区分是哪一个错）
CODE_SERVER_ERROR = 5000  # 未预期的服务端错误


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构造成功响应。"""
    return {"code": CODE_SUCCESS, "message": message, "data": data}


def fail(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造失败响应。"""
    return {"code": code, "message": message, "data": data}
