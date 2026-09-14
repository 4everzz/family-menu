/**
 * 家庭菜谱接口（对接自己的 FastAPI 后端）。
 *
 * 这一层做两件事：
 *   1. 发请求（拼地址、带令牌交给 services/http.ts 统一处理）；
 *   2. 把后端的下划线字段名（created_by_nickname）转成前端驼峰（createdByName）。
 *      转换只在这一个文件里做，页面代码就不用关心后端的命名习惯，
 *      将来后端改字段名也只需要改这里。
 *
 * 关于分类：
 *   菜谱挂的是 category_id（分类 id），不是分类名字符串。
 *   后端额外返回了 category_name，页面直接显示即可，不用自己去分类清单里查。
 *   分类的增删改查在 services/category.ts。
 *
 * 关于权限：菜谱的可见范围由"是不是这个家庭组的成员"决定，这个判断完全在后端，
 * 前端不做也不该做（本地可以被篡改）。非成员调用会拿到 403，由 http.ts 抛成错误。
 *
 * ⚠️ 修改菜谱用的是 POST，不是 PATCH。
 *   后端标准写法是 DELETE/PATCH 这套 REST 语义，PATCH 也确实更准确（部分更新）；
 *   但微信小程序的 wx.request 官方 method 合法值里没有 PATCH，发不出去。
 *   所以后端同一个处理函数挂了两个路由（PATCH + POST），行为完全一致。
 *   详细的坑见 services/http.ts 里 RequestOptions.method 的注释。
 */

import type { Category } from './category';
import { request } from './http';

/** 后端返回的菜谱结构（原始字段，下划线风格） */
interface RecipeDto {
  id: number;
  space_id: number;
  name: string;
  category_id: number;
  category_name: string;
  description: string | null;
  image_url: string | null;
  created_by: number;
  created_by_nickname: string | null;
  created_at: string;
  updated_at: string;
}

/** 分类接口的原始结构（这里只用得上展示字段，完整版在 category.ts） */
interface CategoryDto {
  id: number;
  space_id: number;
  name: string;
  sort_order: number;
  recipe_count: number;
  is_default: boolean;
}

/** 列表接口的返回结构：菜谱数组 + 分类清单 */
interface RecipeListDto {
  categories: CategoryDto[];
  recipes: RecipeDto[];
}

/** 菜谱（前端使用，驼峰风格） */
export interface Recipe {
  /** 菜谱 ID。统一用字符串，方便直接放进页面参数 */
  id: string;
  /** 所属家庭组 ID */
  spaceId: string;
  name: string;
  /** 所属分类 ID，编辑页用它确定当前选中哪个分类 */
  categoryId: string;
  /** 所属分类名，列表和详情直接显示，不用再查一次分类清单 */
  categoryName: string;
  /** 简介，后端没填时统一给空字符串，页面不用判 null */
  description: string;
  /** 图片地址，第一版不做图片上传，基本为空 */
  imageUrl: string;
  /** 添加者昵称，后端查不到时为空字符串 */
  createdByName: string;
  /** 添加者用户 ID，留着以后做"只看我加的"这类功能 */
  createdBy: number;
  /** 最后修改时间（后端返回的 ISO 字符串） */
  updatedAt: string;
}

/** 菜谱列表结果 */
export interface RecipeList {
  /** 分类清单（含每类的菜数和默认选中标记），顺序由后端定义 */
  categories: Category[];
  recipes: Recipe[];
}

/** 新增 / 修改菜谱时提交的字段 */
export interface RecipeInput {
  name: string;
  /** 分类 ID。一道菜必须挂在某个分类下，不能为空 */
  categoryId: string;
  description: string;
  imageUrl: string;
}

/** 把后端字段转成前端结构 */
function toRecipe(dto: RecipeDto): Recipe {
  return {
    id: String(dto.id),
    spaceId: String(dto.space_id),
    name: dto.name,
    categoryId: String(dto.category_id),
    categoryName: dto.category_name,
    // 后端返回 null 表示"没填"，统一成空字符串，页面里就不用到处判空
    description: dto.description || '',
    imageUrl: dto.image_url || '',
    createdByName: dto.created_by_nickname || '',
    createdBy: dto.created_by,
    updatedAt: dto.updated_at,
  };
}

/**
 * 把后端的分类原始结构转成前端结构。
 *
 * 这里刻意和 category.ts 里那份逻辑保持字段一致，但不直接复用函数——
 * 列表接口返回的分类结构和分类接口 1:1 相同，两处都要转，
 * 好在转换规则极简单（下划线换驼峰 + null 兜底），重复的成本低于多一层依赖。
 */
function toCategory(dto: CategoryDto): Category {
  return {
    id: String(dto.id),
    spaceId: String(dto.space_id),
    name: dto.name,
    sortOrder: dto.sort_order,
    recipeCount: dto.recipe_count ?? 0,
    isDefault: Boolean(dto.is_default),
  };
}

/**
 * 拉取某个家庭组的全部菜谱，同时带回分类清单。
 *
 * 为什么两份数据放在一个接口里？
 *   菜单页一次渲染就要用它们两个（侧边栏要分类，右边要菜谱）。
 *   分成两个请求的话，页面会出现"分类栏已经出来了、菜谱还在转圈"的错位感。
 *
 * 为什么不带 category / keyword 参数？
 *   后端这两个筛选参数是可用的，但一个家庭的菜谱通常就几十道，一次全拿回来
 *   在前端过滤，响应是零延迟的，也省掉每敲一个字发一次请求。
 *   等菜谱真的多到几百道，把参数传下去就能切到服务端筛选，接口不用改。
 */
export async function fetchRecipes(spaceId: string): Promise<RecipeList> {
  const dto = await request<RecipeListDto>({ url: `/spaces/${spaceId}/recipes` });
  return {
    categories: (Array.isArray(dto?.categories) ? dto.categories : []).map(toCategory),
    recipes: (Array.isArray(dto?.recipes) ? dto.recipes : []).map(toRecipe),
  };
}

/** 查看单条菜谱详情 */
export async function fetchRecipe(spaceId: string, recipeId: string): Promise<Recipe> {
  const dto = await request<RecipeDto>({ url: `/spaces/${spaceId}/recipes/${recipeId}` });
  return toRecipe(dto);
}

/** 在当前家庭组新增一道菜 */
export async function createRecipe(spaceId: string, input: RecipeInput): Promise<Recipe> {
  const dto = await request<RecipeDto>({
    url: `/spaces/${spaceId}/recipes`,
    method: 'POST',
    data: {
      name: input.name,
      // 后端要的是数字类型的分类 id；页面里为了放进 picker 存的是字符串，这里转一次
      category_id: Number(input.categoryId),
      // 显式传 null 而不是空字符串：后端会把空串也归成"没填"，
      // 但直接给 null 语义更清楚，也少一层转换
      description: input.description.trim() || null,
      image_url: input.imageUrl.trim() || null,
    },
  });
  return toRecipe(dto);
}

/**
 * 修改菜谱（部分更新）。
 *
 * 只把传进来的字段发给后端，没传的字段后端会保持原值。
 * 注意"没传"和"传了空字符串"是两种意图：前者保持原值，后者会清空简介。
 */
export async function updateRecipe(
  spaceId: string,
  recipeId: string,
  input: Partial<RecipeInput>,
): Promise<Recipe> {
  const data: Record<string, unknown> = {};
  if (input.name !== undefined) data.name = input.name;
  if (input.categoryId !== undefined) data.category_id = Number(input.categoryId);
  if (input.description !== undefined) data.description = input.description.trim() || null;
  if (input.imageUrl !== undefined) data.image_url = input.imageUrl.trim() || null;

  const dto = await request<RecipeDto>({
    url: `/spaces/${spaceId}/recipes/${recipeId}`,
    // 这里用 POST 是因为小程序发不出 PATCH，后端两条路由行为一致（见文件头说明）
    method: 'POST',
    data,
  });
  return toRecipe(dto);
}

/** 删除菜谱。后端成功时 data 为 null，所以这里不解析返回值 */
export async function deleteRecipe(spaceId: string, recipeId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/recipes/${recipeId}`, method: 'DELETE' });
}
