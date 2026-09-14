"""个人收藏业务规则。

权限口径：
    收藏是**个人私有域**的数据——不涉及"是不是这个家的人"那种共享判断，
    唯一要过的是两道既有校验：
    1. 收藏一道菜之前，先确认**你能看到它**（菜谱所在家庭组的 ensure_member）。
       拿一个别人家的菜谱 ID 来收藏，应该和"看不见"一样被拒绝。
    2. 指定分区时，确认**这个分区是你的**。分区 ID 是自增的、可猜的，
       不校验归属就能把收藏塞进别人的清单里（对方还会莫名其妙多出一道菜）。

关于「默认收藏夹」（用户拍板的规则）：
    **它不落库**——partition_id 为 NULL 就是默认收藏夹，界面上永远显示在第一位。
    所以这里没有"首次收藏自动建行"的逻辑，也没有"默认收藏夹不能删"的判断
    ——它根本不存在，自然删不掉。
    自定义分区才会落库，用户建一个出一个。

删除自定义分区时，里面的收藏**挪回默认收藏夹**而不是一起删：
    收藏是用户的资产，删一个"文件夹"不该把里面的菜也带走。
    这和菜谱分类的设计（分类下还有菜就不让删）不同——
    分类的约束是保护"菜谱必须有所属"，而收藏即使没有分区也仍然成立（默认栏），
    所以这里可以放心地把收藏退回默认栏。
"""

import logging

from app.core.config import settings
from app.core.exceptions import BusinessError
from app.models.favorite import MAX_PARTITION_NAME_LENGTH
from app.models.user import User
from app.repositories.favorite_repo import FavoriteRepository
from app.services.space_service import SpaceService

logger = logging.getLogger(__name__)


def favorite_partition_quota_for(user: User) -> int:
    """返回该用户可创建的自定义分区数量上限。

    和 space_quota_for 一样的道理：额度**将来会因人而异**（用户说了以后要开会员加次数），
    所以把"取额度"收成这一个函数——将来接会员只改这里，调用方一行不动。
    """
    return settings.max_favorite_partitions


class FavoriteService:
    """收藏服务。"""

    def __init__(self, favorite_repo: FavoriteRepository, space_service: SpaceService) -> None:
        self.repo = favorite_repo
        self.space_service = space_service

    # ==================== 分区 ====================

    async def list_partitions(self, user: User) -> list[tuple[int | None, str, int, bool]]:
        """列出收藏分区（含默认收藏夹），返回 (id, 名字, 数量, 是否默认)。

        默认收藏夹**永远排在第一位**，即使它下面一道菜都没有——
        它是用户最常用的地方，藏起来反而找不到。
        """
        partitions = await self.repo.list_partitions(user.id)
        counts = await self.repo.count_by_partition(user.id)

        result: list[tuple[int | None, str, int, bool]] = [
            (None, "默认收藏夹", counts.get(None, 0), True)
        ]
        for partition in partitions:
            result.append(
                (partition.id, partition.name, counts.get(partition.id, 0), False)
            )
        return result

    async def create_partition(self, user: User, name: str) -> tuple[int, str, int, bool]:
        """新建分区，排在最后。返回 (id, 名字, 0, False)。"""
        cleaned = name.strip()
        if not cleaned:
            raise BusinessError("分区名不能为空")
        if len(cleaned) > MAX_PARTITION_NAME_LENGTH:
            raise BusinessError(f"分区名最多 {MAX_PARTITION_NAME_LENGTH} 个字")

        # 额度只数自定义分区；默认收藏夹是状态，不占额度
        quota = favorite_partition_quota_for(user)
        existing = await self.repo.count_partitions(user.id)
        if existing >= quota:
            raise BusinessError(f"收藏分区数量已达上限（{quota} 个）。删除一个之后可以再创建。")

        # 同一用户内不可重名。对外说"已存在"，不区分"真没有"和"你删过了"——
        # 说得越细，越方便别人拿脚本试探
        for partition in await self.repo.list_partitions(user.id):
            if partition.name == cleaned:
                raise BusinessError(f"已经有叫「{cleaned}」的分区了")

        sort_order = await self.repo.max_sort_order(user.id) + 1
        partition = await self.repo.add_partition(user.id, cleaned, sort_order)
        logger.info("新建收藏分区 | user=%s partition=%s", user.id, partition.id)
        return partition.id, partition.name, 0, False

    async def delete_partition(self, user: User, partition_id: int) -> int:
        """删除分区，里面的收藏退回默认收藏夹。返回挪动的条数（给用户一句确认话术用）。"""
        partition = await self.repo.get_partition(user.id, partition_id)
        if partition is None:
            raise BusinessError("分区不存在", http_status=404)

        moved = await self.repo.move_favorites_to_default(user.id, partition_id)
        await self.repo.delete_partition(partition)
        logger.info(
            "删除收藏分区 | user=%s partition=%s moved=%s", user.id, partition_id, moved
        )
        return moved

    # ==================== 收藏 ====================

    async def favorite(
        self, user: User, recipe_id: int, partition_id: int | None
    ) -> tuple[int, int | None, bool]:
        """收藏一道菜（或把已有收藏挪到指定分区）。

        返回 (菜谱 ID, 分区 ID, 是否新建)。
        已收藏过时不是报错，而是**挪到目标分区**——
        这样"点提示改分区"和"收藏到指定分区"能共用这一个接口。
        """
        recipe = await self.repo.get_recipe(recipe_id)
        if recipe is None:
            raise BusinessError("这道菜不存在", http_status=404)

        # 你得先能看到这道菜，才能收藏它（是否这个家的人，复用既有校验）
        await self.space_service.ensure_member(recipe.space_id, user.id)

        if partition_id is not None:
            partition = await self.repo.get_partition(user.id, partition_id)
            if partition is None:
                raise BusinessError("分区不存在", http_status=404)

        existing = await self.repo.get_favorite(user.id, recipe_id)
        if existing is not None:
            updated = await self.repo.update_favorite_partition(existing, partition_id)
            return updated.recipe_id, updated.partition_id, False

        favorite = await self.repo.add_favorite(user.id, recipe_id, partition_id)
        logger.info("收藏菜谱 | user=%s recipe=%s partition=%s", user.id, recipe_id, partition_id)
        return favorite.recipe_id, favorite.partition_id, True

    async def unfavorite(self, user: User, recipe_id: int) -> None:
        """取消收藏。没收藏过时给出 404，让前端的双重点击能被发现而不是静默成功。"""
        favorite = await self.repo.get_favorite(user.id, recipe_id)
        if favorite is None:
            raise BusinessError("你还没有收藏这道菜", http_status=404)
        await self.repo.delete_favorite(favorite)

    async def list_favorites(
        self, user: User, partition_id: int | None
    ) -> list[tuple[object, object, str, str | None]]:
        """列出某分区下的收藏（含菜谱摘要、家庭组名、分类名），按收藏时间倒序。

        partition_id 传 None 表示默认收藏夹（不是"全部"）。
        指定了分区就先确认它是自己的——否则别人的分区 ID 也能查。
        """
        if partition_id is not None:
            partition = await self.repo.get_partition(user.id, partition_id)
            if partition is None:
                raise BusinessError("分区不存在", http_status=404)
        return await self.repo.list_favorites(user.id, partition_id)

    async def list_favorited_recipe_ids(self, user: User, space_id: int) -> list[int]:
        """列出用户在某家庭组里已收藏的菜谱 ID（菜单页画星标用）。

        先确认是那个家的人——虽然 ID 列表泄露不了什么，
        但"非成员连家存不存在都不该知道"这条原则在这里同样适用。
        """
        await self.space_service.ensure_member(space_id, user.id)
        return await self.repo.list_favorited_recipe_ids(user.id, space_id)
