"""个人健康档案的业务规则。

为什么单独一个 Service，而不是在接口里直接改几个字段？
    因为"改健康档案"看着只是存几个数，实际有几条规则要守：
      · 性别/目标只能是白名单里的几个值，不能让用户塞任意字符串；
      · 身高/体重要在合理范围（过界大概率是手抖输错，比如把 1.75 输成 175）；
      · 饮食备注有长度上限；
      · 这些规则将来一旦要加（比如 BMI 预警、敏感词），只改这一处，所有入口都跟着变。

接口层（app/api/v1/user_profile.py）只负责收参数、调这里、返回结果。
"""

from datetime import date

from app.core.exceptions import BusinessError
from app.models.user import User
from app.models.user_profile import (
    GOAL_GAIN,
    GOAL_LOSE,
    GOAL_MAINTAIN,
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_OTHER,
    MAX_DIET_PREFERENCES_LENGTH,
    CalorieLog,
    UserProfile,
)
from app.repositories.calorie_log_repo import CalorieLogRepository
from app.repositories.user_profile_repo import UserProfileRepository

# 身高/体重的合理范围（过界大概率是手抖输错）
HEIGHT_CM_MIN, HEIGHT_CM_MAX = 50, 250
WEIGHT_KG_MIN, WEIGHT_KG_MAX = 2, 300


class UserProfileService:
    """个人健康档案相关业务。"""

    def __init__(
        self,
        profile_repo: UserProfileRepository,
        log_repo: CalorieLogRepository,
    ) -> None:
        self.profile_repo = profile_repo
        self.log_repo = log_repo

    # ==================== 档案 ====================

    async def get_profile(self, user: User) -> UserProfile | None:
        """取当前用户的健康档案（可能还没有，返回 None）。"""
        return await self.profile_repo.get_by_user_id(user.id)

    async def update_profile(self, user: User, changes: dict) -> UserProfile:
        """按传入字段更新健康档案。

        参数 changes 只包含请求体里**真正出现过**的键（接口层用 exclude_unset 得到），
        没出现的键保持原值，出现了但值为 null 的表示清空。
        """
        if not changes:
            raise BusinessError("没有需要修改的内容")

        cleaned: dict = {}
        if "gender" in changes:
            cleaned["gender"] = self._clean_gender(changes["gender"])
        if "height_cm" in changes:
            cleaned["height_cm"] = self._clean_decimal(
                changes["height_cm"], HEIGHT_CM_MIN, HEIGHT_CM_MAX, "身高"
            )
        if "weight_kg" in changes:
            cleaned["weight_kg"] = self._clean_decimal(
                changes["weight_kg"], WEIGHT_KG_MIN, WEIGHT_KG_MAX, "体重"
            )
        if "goal" in changes:
            cleaned["goal"] = self._clean_goal(changes["goal"])
        if "diet_preferences" in changes:
            cleaned["diet_preferences"] = self._clean_text(
                changes["diet_preferences"], MAX_DIET_PREFERENCES_LENGTH, "饮食备注"
            )

        return await self.profile_repo.upsert(user.id, cleaned)

    # ==================== 热量记录 ====================

    async def list_logs(
        self, user: User, date_from: date | None = None, date_to: date | None = None
    ) -> list[CalorieLog]:
        """列出某用户的热量记录（可按日期区间）。"""
        return await self.log_repo.list_by_user(user.id, date_from, date_to)

    async def add_log(self, user: User, data: dict) -> CalorieLog:
        """新增一条热量记录。"""
        if not data.get("food_name") or not str(data["food_name"]).strip():
            raise BusinessError("请填写食物名称")
        if data.get("calories") is None:
            raise BusinessError("请填写热量")

        payload = {
            "food_name": str(data["food_name"]).strip(),
            "calories": self._to_decimal(data["calories"], "热量"),
            "eaten_at": data.get("eaten_at") or date.today(),
            "portion": str(data["portion"]).strip() if data.get("portion") else None,
            "image_url": data.get("image_url"),
            "source": data.get("source") or "vision",
        }
        return await self.log_repo.add(user.id, payload)

    async def delete_log(self, user: User, log_id: int) -> None:
        """删除一条热量记录（先校验归属）。"""
        log = await self.log_repo.get_owned(user.id, log_id)
        if log is None:
            raise BusinessError("记录不存在")
        await self.log_repo.delete(log)

    # ==================== 内部校验 ====================

    @staticmethod
    def _clean_gender(value) -> str | None:
        if value is None:
            return None
        value = str(value).strip().lower()
        if value not in (GENDER_MALE, GENDER_FEMALE, GENDER_OTHER):
            raise BusinessError("性别取值不合法（male/female/other）")
        return value

    @staticmethod
    def _clean_goal(value) -> str | None:
        if value is None:
            return None
        value = str(value).strip().lower()
        if value not in (GOAL_LOSE, GOAL_MAINTAIN, GOAL_GAIN):
            raise BusinessError("目标取值不合法（lose/maintain/gain）")
        return value

    @staticmethod
    def _clean_decimal(value, low: float, high: float, label: str):
        if value is None:
            return None
        try:
            d = float(value)
        except (TypeError, ValueError):
            raise BusinessError(f"{label}必须是数字")
        if d < low or d > high:
            raise BusinessError(f"{label}应在 {low}–{high} 之间")
        return round(d, 1)

    @staticmethod
    def _clean_text(value, max_len: int, label: str) -> str | None:
        if value is None:
            return None
        s = str(value)
        if len(s) > max_len:
            raise BusinessError(f"{label}最多 {max_len} 字")
        return s

    @staticmethod
    def _to_decimal(value, label: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise BusinessError(f"{label}必须是数字")
