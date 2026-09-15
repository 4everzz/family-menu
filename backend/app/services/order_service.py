"""点单业务规则。

权限口径（和菜单/冰箱有一处**刻意的不同**）：
    提交点单  —— **任何家庭成员都能做**。点单是"提需求"，不是"改菜单"；
                客人拿创建人手机点时，提交者就是创建人。
    管理点单  —— **创建人** 或 **提交者本人** 可以改状态、删除。

    为什么管理权不像菜单/冰箱那样一律收给创建人？
        菜单和冰箱是**长期共享的资料**，谁都能改 = 谁都能清空别人记的东西，代价不可逆；
        点单是**一次性的请求**，提错了想自己撤掉是很自然的事。
        但也不能让不相干的人碰，所以把范围钉在"创建人 + 提交者本人"两个身份上。

安全原则（和菜谱/冰箱一致）：
    · "是不是家庭成员""是不是创建人"必须由后端查库判断，统一走
      SpaceService.ensure_member / ensure_owner；
    · 点单 ID 和菜谱 ID 都是自增可猜的，每个接口都要确认它属于这个家庭组，
      否则拿自己的 space_id 配别人家的 ID 就能越权。
"""

from app.core.exceptions import BusinessError, NotFoundError
from app.models.dish_order import (
    MAX_ITEM_QUANTITY,
    ORDER_STATUS_PENDING,
    DishOrder,
    DishOrderItem,
)
from app.models.recipe import Recipe
from app.models.user import User
from app.repositories.order_repo import OrderRepository
from app.services.space_service import SpaceService


class OrderService:
    """点单服务。"""

    def __init__(self, repo: OrderRepository, space_service: SpaceService) -> None:
        self.repo = repo
        # 复用家庭组的成员/创建人校验，鉴权只有一份实现
        self.space_service = space_service

    # ==================== 读操作 ====================

    async def list_orders(
        self,
        user: User,
        space_id: int,
        status: str | None = None,
    ) -> tuple[list[tuple[DishOrder, str, list[DishOrderItem]]], bool]:
        """列出这个家的点单，新的在前。

        返回 ([(点单, 提交者昵称, 明细列表), ...], 我是不是创建人)。
        任何成员都能看——点单本来就是给全家人看的"今天要做什么菜"。

        为什么把"我是不是创建人"一起返回？
            列表上每条单要显示不显示"标记完成 / 删除"，取决于"创建人 或 提交者本人"。
            这个判断放在后端做，前端就永远和后端口径一致——
            否则前端自己拿本地缓存的角色去算，规则一改就会出现
            "按钮看得到、点下去被 403"，那是最难查的一类问题。
        """
        space, _ = await self.space_service.ensure_member(space_id, user.id)
        rows = await self.repo.list_by_space(space_id, status)
        grouped = await self.repo.list_items_grouped([order.id for order, _ in rows])
        detailed = [(order, nickname, grouped.get(order.id, [])) for order, nickname in rows]
        return detailed, space.owner_id == user.id

    # ==================== 写操作 ====================

    async def create_order(
        self,
        user: User,
        space_id: int,
        *,
        guest_name: str | None,
        remark: str | None,
        items: list[tuple[int, int, str | None]],
    ) -> tuple[DishOrder, list[DishOrderItem]]:
        """提交点单。items 是 (菜谱 ID, 份数, 辣度) 的列表。

        返回 (点单, 明细)，方便接口层直接组装响应，不用再查一次。
        """
        await self.space_service.ensure_member(space_id, user.id)

        # ---------- 1. 同一道菜 + 同一个辣度才算一条，重复的合并份数 ----------
        # 键里必须带上辣度：一份微辣、一份特辣是同一种菜的两条明细，
        # 合成一条会把客人要的口味弄丢。
        # 前端购物车里同一道菜已经按辣度分成两行，但接口是公开的、直接调的人可能重复传，
        # 这里兜一层，保证库里不会出现两行完全一样的明细。
        merged: dict[tuple[int, str | None], int] = {}
        for recipe_id, quantity, spice in items:
            key = (recipe_id, spice)
            merged[key] = merged.get(key, 0) + quantity
            if merged[key] > MAX_ITEM_QUANTITY:
                raise BusinessError(f"单道菜最多点 {MAX_ITEM_QUANTITY} 份")

        # ---------- 2. 确认这些菜谱都属于这个家庭组 ----------
        recipe_ids = list({recipe_id for recipe_id, _ in merged})
        recipes = await self.repo.get_recipes_in_space(space_id, recipe_ids)
        if len(recipes) != len(recipe_ids):
            # 不说是哪一道不对：说得越细，越方便别人拿脚本试探哪些 ID 是真实存在的
            raise BusinessError("有点的菜不在这个家庭的菜单里，请刷新菜单后重试")

        # ---------- 3. 校验「今天不做」与辣度 ----------
        for recipe_id, _spice in merged:
            recipe = recipes[recipe_id]
            if recipe.is_sold_out:
                raise BusinessError(f"「{recipe.name}」今天不做，先把它去掉再提交")

        for recipe_id, spice in merged:
            # 前端已经限定了可选范围，但接口是公开的——别人绕过界面直接调，
            # 就可能存进一个这道菜根本没有的辣度，做饭的人看到会莫名其妙
            recipe = recipes[recipe_id]
            if spice is not None and spice not in (recipe.spice_options or []):
                raise BusinessError(f"「{recipe.name}」没有「{spice}」这个辣度，请重新选择")

        # ---------- 4. 组装明细，存下菜名与辣度快照 ----------
        # 存快照是为了"以后菜谱改名、改辣度档位甚至删掉，这条历史点单依然说得清当时要的是什么"
        detail_rows = [
            (
                recipe_id,
                recipes[recipe_id].name,
                self._resolve_spice(recipes[recipe_id], spice),
                quantity,
            )
            for (recipe_id, spice), quantity in merged.items()
        ]

        order = await self.repo.create_order(
            space_id=space_id,
            created_by=user.id,
            guest_name=guest_name,
            remark=remark,
            status=ORDER_STATUS_PENDING,
            items=detail_rows,
        )
        # create_order 已经 flush 过明细，这里直接按 id 取回来（顺序与插入一致）
        grouped = await self.repo.list_items_grouped([order.id])
        return order, grouped.get(order.id, [])

    async def update_status(
        self,
        user: User,
        space_id: int,
        order_id: int,
        status: str,
    ) -> tuple[DishOrder, str, list[DishOrderItem]]:
        """改点单状态（待处理 / 已完成）。"""
        order, nickname = await self._get_managed_order(user, space_id, order_id)
        order.status = status
        await self.repo.save(order)

        grouped = await self.repo.list_items_grouped([order.id])
        return order, nickname, grouped.get(order.id, [])

    async def delete_order(self, user: User, space_id: int, order_id: int) -> None:
        """删除点单。明细靠外键 CASCADE 一起清掉。"""
        order, _ = await self._get_managed_order(user, space_id, order_id)
        await self.repo.delete_order(order)

    # ==================== 内部工具 ====================

    @staticmethod
    def _resolve_spice(recipe: Recipe, spice: str | None) -> str | None:
        """决定这条明细最终记下什么辣度。

        客人明确选了就用他的选择。没选（比如前端漏传）时：
        这道菜有辣度档位就落成它的默认档，完全没有档位才留空。

        为什么要兜这一层，而不是直接存 None？
            点单是一条**历史记录**。对着一条辣度空白的明细，
            做饭的人没法判断"当时到底是没要求，还是没人问他"——
            而有默认档就落默认档，"这单要什么口味"就永远说得清。
        """
        if spice is not None:
            return spice
        if recipe.spice_options:
            return recipe.default_spice or recipe.spice_options[0]
        return None

    async def _get_managed_order(
        self,
        user: User,
        space_id: int,
        order_id: int,
    ) -> tuple[DishOrder, str]:
        """取出点单并校验"这个人能不能管它"。返回 (点单, 提交者昵称)。

        查不到、不属于这个家，对外统一说"点单不存在"（404），不区分两种情况——
        说得越细，越方便别人拿脚本试探哪些 ID 是真的。
        """
        # 先确认真的是这个家的成员（下面 created_by 的判断依赖这一点）
        await self.space_service.ensure_member(space_id, user.id)

        found = await self.repo.get_order_with_nickname(order_id)
        if found is None:
            raise NotFoundError("点单不存在")
        order, nickname = found

        if order.space_id != space_id:
            raise NotFoundError("点单不存在")

        # 提交者本人可以管自己的单；其他人必须是创建人
        if order.created_by != user.id:
            await self.space_service.ensure_owner(space_id, user.id)

        return order, nickname
