/**
 * 个人收藏的服务层。
 *
 * 收藏是**个人私有域**的数据（跟着 user_id 走），和家庭共享域（菜谱、分类）刻意分开：
 * 同一个家里的两个人，各自收藏各自的，互相看不见。
 *
 * 一个容易理解错的点：**默认收藏夹不是一个 ID**。
 * 后端把它设计成「partition_id 为 NULL」这个状态，所以它永远存在、
 * 排在第一位、也删不掉——前端拿到的分区列表里，它的 id 是 null。
 */

import { request } from './http';

/** 后端返回的分区结构（原始字段） */
interface PartitionDto {
  id: number | null;
  name: string;
  count: number;
  isDefault: boolean;
}

/** 收藏分区 */
export interface FavoritePartition {
  /** 分区 ID。null = 默认收藏夹（它不是一行数据，是一个状态） */
  id: number | null;
  name: string;
  /** 这个分区下有几道收藏的菜 */
  count: number;
  isDefault: boolean;
}

/** 后端返回的收藏条目（原始字段） */
interface FavoriteItemDto {
  recipeId: number;
  name: string;
  description: string | null;
  image_url: string | null;
  spaceId: number;
  spaceName: string;
  categoryName: string | null;
  partitionId: number | null;
  favoritedAt: string;
}

/** 收藏列表里的一条 */
export interface FavoriteItem {
  /** 菜谱 ID。统一用字符串，方便直接放进页面参数 */
  recipeId: string;
  name: string;
  description: string | null;
  spaceId: string;
  spaceName: string;
  categoryName: string | null;
  favoritedAt: string;
}

/** 收藏分区列表（默认收藏夹永远在第一位） */
export async function fetchPartitions(): Promise<FavoritePartition[]> {
  const list = await request<PartitionDto[]>({ url: '/favorites/partitions' });
  return list.map((item) => ({
    id: item.id,
    name: item.name,
    count: item.count,
    isDefault: item.isDefault,
  }));
}

/** 新建收藏分区，排在最后。数量有上限（后端配置） */
export async function createPartition(name: string): Promise<FavoritePartition> {
  const dto = await request<PartitionDto>({
    url: '/favorites/partitions',
    method: 'POST',
    data: { name },
  });
  return { id: dto.id, name: dto.name, count: dto.count, isDefault: dto.isDefault };
}

/** 删除分区。里面的收藏会退回默认收藏夹（收藏本身不丢），返回挪动的条数 */
export async function deletePartition(partitionId: number): Promise<number> {
  const data = await request<{ moved: number }>({
    url: `/favorites/partitions/${partitionId}`,
    method: 'DELETE',
  });
  return data.moved;
}

/** 收藏列表。partitionId 传 null 即默认收藏夹 */
export async function fetchFavorites(partitionId: number | null): Promise<FavoriteItem[]> {
  const data = await request<{ favorites: FavoriteItemDto[]; total: number }>({
    url: '/favorites',
    data: partitionId === null ? {} : { partition_id: partitionId },
  });
  return data.favorites.map((item) => ({
    recipeId: String(item.recipeId),
    name: item.name,
    description: item.description,
    spaceId: String(item.spaceId),
    spaceName: item.spaceName,
    categoryName: item.categoryName,
    favoritedAt: item.favoritedAt,
  }));
}

/**
 * 收藏一道菜。partitionId 传 null 即默认收藏夹。
 * 已收藏过时后端不会报错，而是把收藏**挪到**指定分区——
 * 「点提示改分区」和「直接收藏到某分区」共用这一个接口。
 */
export async function favoriteRecipe(recipeId: string, partitionId: number | null): Promise<void> {
  await request({
    url: `/favorites/${recipeId}`,
    method: 'POST',
    data: partitionId === null ? {} : { partition_id: partitionId },
  });
}

/** 取消收藏。没收藏过时后端返回 404（双重点击不该被静默吞掉） */
export async function unfavoriteRecipe(recipeId: string): Promise<void> {
  await request({ url: `/favorites/${recipeId}`, method: 'DELETE' });
}

/**
 * 我在某个家庭组里已收藏的菜谱 ID（菜单页画星标用）。
 * 只返回 ID 列表，一次轻量查询。
 */
export async function fetchFavoritedIds(spaceId: string): Promise<Set<string>> {
  const ids = await request<number[]>({
    url: '/favorites/recipe-ids',
    data: { space_id: spaceId },
  });
  return new Set(ids.map(String));
}
