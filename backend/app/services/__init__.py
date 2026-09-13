"""业务规则层（Service）：写"什么情况下能做、什么情况下不允许"。"""

from app.services.auth_service import AuthService

__all__ = ["AuthService"]
