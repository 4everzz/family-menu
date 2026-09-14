/**
 * 家庭冰箱接口（对接自己的 FastAPI 后端）。
 *
 * 这一层和 services/recipe.ts 是同一套写法：
 *   1. 发请求交给 services/http.ts 统一处理（拼地址、带令牌、解析 { code, message, data }）；
 *   2. 把后端下划线字段（created_by_nickname）转成前端驼峰（createdByName），
 *      转换只在这一个文件做，页面不用关心后端命名习惯。
 *
 * 关于权限：冰箱也是"家庭共享域"，可见范围由"是不是这个家庭成员"决定，判断全在后端。
 * 普通成员只能看，不能改——前端把增删改入口藏起来只是体验，真正的拦截在
 * SpaceService.ensure_owner（非创建人调写接口直接 403）。
 *
 * ⚠️ 修改用的是 PUT，不是 PATCH。
 *   菜谱因为小程序发不出 PATCH，后端额外开了 POST 副本；冰箱直接走 PUT，
 *   因为微信小程序的 wx.request 官方 method 合法值里**有 PUT**（没有的只是 PATCH）。
 *   所以冰箱不需要那套 POST 副本，接口更干净。
 */

import { request } from './http';

/** 后端返回的食材结构（原始字段，下划线风格） */
interface FridgeItemDto {
  id: number;
  space_id: number;
  name: string;
  quantity: number;
  unit: string | null;
  category: string | null;
  storage: string | null;
  expiry_date: string | null;
  note: string | null;
  is_expiring: boolean;
  created_by: number;
  created_by_nickname: string | null;
  created_at: string;
  updated_at: string;
}

/** 列表接口返回结构：食材数组 + 临期件数 */
interface FridgeListDto {
  items: FridgeItemDto[];
  expiring_count: number;
}

/** 食材（前端使用，驼峰风格） */
export interface FridgeItem {
  id: string;
  spaceId: string;
  name: string;
  /** 数量（数字，配合 unit 显示，如 10 + 个） */
  quantity: number;
  /** 单位，后端没填时统一成空字符串 */
  unit: string;
  /** 分类，后端没填时为空字符串 */
  category: string;
  /** 存放位置，后端没填时为空字符串 */
  storage: string;
  /** 保质期（YYYY-MM-DD），没有则 null */
  expiryDate: string | null;
  /** 备注，后端没填时为空字符串 */
  note: string;
  /** 是否临近过期或已过期（后端按今天+7天窗口算出） */
  isExpiring: boolean;
  /** 添加者昵称，后端查不到时为空字符串 */
  createdByName: string;
  createdAt: string;
  updatedAt: string;
}

/** 列表结果 */
export interface FridgeList {
  items: FridgeItem[];
  /** 临期/过期件数（与当前筛选无关，统计整个家庭组） */
  expiringCount: number;
}

/** 新增 / 修改食材时提交的字段 */
export interface FridgeInput {
  name: string;
  quantity: number;
  unit: string;
  category: string;
  storage: string;
  expiryDate: string | null;
  note: string;
}

/** 把后端字段转成前端结构，null 一律兜底成空字符串/空 */
function toItem(dto: FridgeItemDto): FridgeItem {
  return {
    id: String(dto.id),
    spaceId: String(dto.space_id),
    name: dto.name,
    quantity: dto.quantity,
    unit: dto.unit || '',
    category: dto.category || '',
    storage: dto.storage || '',
    expiryDate: dto.expiry_date || null,
    note: dto.note || '',
    isExpiring: dto.is_expiring,
    createdByName: dto.created_by_nickname || '',
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

/** 列表查询参数（分类 / 存放 / 关键词，都是可选筛选） */
export interface FridgeQuery {
  category?: string;
  storage?: string;
  keyword?: string;
}

/**
 * 拉取某个家庭组的冰箱食材。
 *
 * 为什么把筛选交给后端而不是前端全拿回来自己筛？
 *   冰箱数据量比菜谱大（一个家几十到几百条），而且临期提示需要"整个家庭组"的计数，
 *   前端只拿筛选后的子集会算错横幅数字。所以分类/存放/关键词都传给后端，
 *   后端同时把 expiring_count 算好一并返回。
 */
export async function fetchFridge(spaceId: string, query: FridgeQuery = {}): Promise<FridgeList> {
  const parts: string[] = [];
  if (query.category) parts.push(`category=${encodeURIComponent(query.category)}`);
  if (query.storage) parts.push(`storage=${encodeURIComponent(query.storage)}`);
  if (query.keyword) parts.push(`keyword=${encodeURIComponent(query.keyword)}`);
  const qs = parts.length ? `?${parts.join('&')}` : '';

  const dto = await request<FridgeListDto>({ url: `/spaces/${spaceId}/fridge${qs}` });
  return {
    items: (Array.isArray(dto?.items) ? dto.items : []).map(toItem),
    expiringCount: dto?.expiring_count ?? 0,
  };
}

/** 查看单条食材详情 */
export async function fetchFridgeItem(spaceId: string, itemId: string): Promise<FridgeItem> {
  const dto = await request<FridgeItemDto>({ url: `/spaces/${spaceId}/fridge/${itemId}` });
  return toItem(dto);
}

/** 在当前家庭组新增一件食材（仅创建人） */
export async function createFridgeItem(spaceId: string, input: FridgeInput): Promise<FridgeItem> {
  const dto = await request<FridgeItemDto>({
    url: `/spaces/${spaceId}/fridge`,
    method: 'POST',
    data: {
      name: input.name,
      quantity: input.quantity,
      // 显式传 null 而不是空字符串：后端把空串也归成"没填"，直接给 null 语义更清楚
      unit: input.unit.trim() || null,
      category: input.category.trim() || null,
      storage: input.storage.trim() || null,
      expiry_date: input.expiryDate || null,
      note: input.note.trim() || null,
    },
  });
  return toItem(dto);
}

/**
 * 修改食材（部分更新，仅创建人）。
 * 只把传进来的字段发给后端，没传的字段后端保持原值。
 */
export async function updateFridgeItem(
  spaceId: string,
  itemId: string,
  input: Partial<FridgeInput>,
): Promise<FridgeItem> {
  const data: Record<string, unknown> = {};
  if (input.name !== undefined) data.name = input.name;
  if (input.quantity !== undefined) data.quantity = input.quantity;
  if (input.unit !== undefined) data.unit = input.unit.trim() || null;
  if (input.category !== undefined) data.category = input.category.trim() || null;
  if (input.storage !== undefined) data.storage = input.storage.trim() || null;
  if (input.expiryDate !== undefined) data.expiry_date = input.expiryDate || null;
  if (input.note !== undefined) data.note = input.note.trim() || null;

  const dto = await request<FridgeItemDto>({
    url: `/spaces/${spaceId}/fridge/${itemId}`,
    method: 'PUT',
    data,
  });
  return toItem(dto);
}

/** 删除食材（仅创建人） */
export async function deleteFridgeItem(spaceId: string, itemId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/fridge/${itemId}`, method: 'DELETE' });
}
