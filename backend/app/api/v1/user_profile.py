"""个人健康档案接口。

路径统一用 /users/me 前缀，身份从令牌解析，前端不传 user_id（和 users.py 一致，
从接口形状上就杜绝"改/看别人档案"的可能）。
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.response import success
from app.repositories.calorie_log_repo import CalorieLogRepository
from app.repositories.user_profile_repo import UserProfileRepository
from app.schemas.user_profile import (
    CalorieLogCreate,
    CalorieLogResponse,
    HealthProfileResponse,
    HealthProfileUpdate,
)
from app.services.user_profile_service import UserProfileService

router = APIRouter(tags=["健康档案"])


def _service(session: DbSession) -> UserProfileService:
    """接口层只负责组装依赖，业务规则都在 Service。"""
    return UserProfileService(UserProfileRepository(session), CalorieLogRepository(session))


@router.get("/users/me/health-profile", summary="获取健康档案")
async def get_health_profile(current_user: CurrentUser, session: DbSession) -> dict:
    """返回当前登录用户的健康档案；还没有则返回 null。"""
    profile = await _service(session).get_profile(current_user)
    if profile is None:
        return success(None)
    return success(HealthProfileResponse.model_validate(profile).model_dump())


@router.patch("/users/me/health-profile", summary="修改健康档案")
@router.post(
    "/users/me/health-profile",
    summary="修改健康档案（小程序端入口）",
    description=(
        "与 PATCH 行为完全一致，仅因微信小程序的 wx.request 不支持 PATCH 而额外开放。"
        "小程序端请使用本入口，App / H5 端用标准的 PATCH。"
    ),
)
async def update_health_profile(
    payload: HealthProfileUpdate,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """修改健康档案（部分更新）。exclude_unset 取出真正出现过的字段交给 Service。"""
    profile = await _service(session).update_profile(
        current_user, payload.model_dump(exclude_unset=True)
    )
    await session.commit()
    return success(HealthProfileResponse.model_validate(profile).model_dump())


@router.get("/users/me/calorie-logs", summary="热量记录列表")
async def list_calorie_logs(
    current_user: CurrentUser,
    session: DbSession,
    date_from: Optional[date] = Query(default=None, description="起始日期 yyyy-mm-dd"),
    date_to: Optional[date] = Query(default=None, description="结束日期 yyyy-mm-dd"),
) -> dict:
    """列出当前用户的热量记录，按日期倒序；可按日期区间过滤。"""
    logs = await _service(session).list_logs(current_user, date_from, date_to)
    return success([CalorieLogResponse.model_validate(log).model_dump() for log in logs])


@router.post("/users/me/calorie-logs", summary="新增热量记录")
async def create_calorie_log(
    payload: CalorieLogCreate,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """新增一条热量记录（拍照识别或手动添加）。"""
    log = await _service(session).add_log(current_user, payload.model_dump())
    await session.commit()
    return success(CalorieLogResponse.model_validate(log).model_dump())


@router.delete("/users/me/calorie-logs/{log_id}", summary="删除热量记录")
async def delete_calorie_log(
    log_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """删除一条热量记录（先校验归属，不是你的会报"记录不存在"）。"""
    await _service(session).delete_log(current_user, log_id)
    await session.commit()
    return success(None)
