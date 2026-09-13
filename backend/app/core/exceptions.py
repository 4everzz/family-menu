"""业务异常与全局异常处理。

设计思路：
    Service 层遇到"规则不允许"的情况（比如账号被停用），直接抛业务异常，
    不用在每个接口里写 try/except 再拼返回结构——这里统一兜住并转成 { code, message, data }。
    接口代码因此变得很薄：只负责收参数、调 Service、返回结果。
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import (
    CODE_BUSINESS,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_PARAM_INVALID,
    CODE_SERVER_ERROR,
    CODE_UNAUTHORIZED,
    fail,
)

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """业务异常基类：由 Service 层主动抛出，表示业务规则不允许继续。"""

    def __init__(
        self,
        message: str,
        code: int = CODE_BUSINESS,
        http_status: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


class UnauthorizedError(BusinessError):
    """未登录，或令牌无效/过期。"""

    def __init__(self, message: str = "请先登录") -> None:
        super().__init__(message, code=CODE_UNAUTHORIZED, http_status=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(BusinessError):
    """已登录，但没有操作权限（例如不是该家庭组成员）。"""

    def __init__(self, message: str = "没有操作权限") -> None:
        super().__init__(message, code=CODE_FORBIDDEN, http_status=status.HTTP_403_FORBIDDEN)


class NotFoundError(BusinessError):
    """请求的数据不存在。"""

    def __init__(self, message: str = "数据不存在") -> None:
        super().__init__(message, code=CODE_NOT_FOUND, http_status=status.HTTP_404_NOT_FOUND)


def register_exception_handlers(app: FastAPI) -> None:
    """把各类异常统一转换成固定返回格式。"""

    @app.exception_handler(BusinessError)
    async def _handle_business_error(request: Request, exc: BusinessError) -> JSONResponse:
        """业务异常：这是预期内的错误，用 info 级别记录即可，不打堆栈。"""
        logger.info("业务异常 | %s %s | code=%s | %s", request.method, request.url.path, exc.code, exc.message)
        return JSONResponse(status_code=exc.http_status, content=fail(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """参数校验失败：把 Pydantic 的错误信息转成前端能直接展示的文案。"""
        errors = exc.errors()
        first = errors[0] if errors else {}
        # loc 形如 ('body', 'code')，去掉 body 后拼成 "code"
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"参数不合法：{location} {first.get('msg', '')}".strip()
        logger.info("参数校验失败 | %s %s | %s", request.method, request.url.path, message)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=fail(CODE_PARAM_INVALID, message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """框架层抛出的 HTTP 异常（例如路由不存在）。"""
        return JSONResponse(status_code=exc.status_code, content=fail(exc.status_code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """未预期的异常：日志里保留完整堆栈方便排查，返回给前端的信息保持简洁。

        注意这里只对外说"服务器内部错误"，不把堆栈或数据库细节暴露出去——
        那些信息对攻击者有用，对用户没用。
        """
        logger.exception("未处理的异常 | %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=fail(CODE_SERVER_ERROR, "服务器内部错误，请稍后重试"),
        )
