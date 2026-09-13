/**
 * 菜谱分类接口（对接自己的 FastAPI 后端）。
 *
 * 分类是"每个家庭组各自一套"的数据，所以所有接口都挂在 /spaces/{空间}/categories 下面。
 * 下划线 → 驼峰的转换只在本文件里做，页面代码不用关心后端的命名习惯。
 *
 * ⚠️ 改名用的是 POST，不是 PATCH。
 *   后端按标准 REST 语义把"修改分类"做成了 PATCH，
 *   但微信小程序的 wx.request 官方 method 合法值里没有 PATCH，发不出去。
 *   所以后端同一个处理函数挂了两个路由（PATCH + POST），行为完全一致。
 *   详见 services/http.ts 里 RequestOptions.method 的注释。
 */

import { request } from './http';

/** 后端返回的分类结构（原始字段，下划线风格） */
interface CategoryDto {
  id: number;
  space_id: number;
  name: string;
  sort_order: number;
  recipe_count: number;
  is_default: boolean;
}

/** 菜谱分类（前端使用，驼峰风格） */
export interface Category {
  /** 分类 ID。统一用字符串，方便直接放进页面参数和 picker 的值 */
  id: string;
  spaceId: string;
  /** 分类名，例如「热菜」 */
  name: string;
  /** 显示顺序，数字越小越靠前。顺序由后端给，前端不自己排 */
  sortOrder: number;
  /**
   * 该分类下的菜谱数量（全量口径，不受搜索/筛选影响）。
   * 后端算好给前端，避免前端拿过滤后的列表去数，数出来和侧边栏对不上。
   */
  recipeCount: number;
  /**
   * 是否为「新增菜品时默认选中」的分类。
   * 前端不要自己硬编码「热菜」这个字符串——用户可以把它改名，
   * 硬编码的话改名之后默认选中就悄悄失效了。
   */
  isDefault: boolean;
}

/** 把后端字段转成前端结构 */
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
 * 拉取某个家庭组的全部分类。
 *
 * 返回顺序就是侧边栏的显示顺序，前端直接照用，不要自己再排一遍。
 */
export async function fetchCategories(spaceId: string): Promise<Category[]> {
  const list = await request<CategoryDto[]>({ url: `/spaces/${spaceId}/categories` });
  return (Array.isArray(list) ? list : []).map(toCategory);
}

/** 新增一个分类。后端会把它排在现有分类的最后面 */
export async function createCategory(spaceId: string, name: string): Promise<Category> {
  const dto = await request<CategoryDto>({
    url: `/spaces/${spaceId}/categories`,
    method: 'POST',
    data: { name: name.trim() },
  });
  return toCategory(dto);
}

/** 给分类改名。挂在它下面的菜谱会自动显示新名字，不用逐个去改 */
export async function renameCategory(
  spaceId: string,
  categoryId: string,
  name: string,
): Promise<Category> {
  const dto = await request<CategoryDto>({
    url: `/spaces/${spaceId}/categories/${categoryId}`,
    // 用 POST 是因为小程序发不出 PATCH，后端两条路由行为一致（见文件头说明）
    method: 'POST',
    data: { name: name.trim() },
  });
  return toCategory(dto);
}

/**
 * 删除一个分类。
 *
 * 分类下还有菜谱时后端会拒绝（400 并带上"还有几道菜"的提示），
 * 这里不吞掉错误——由调用方 catch 之后把提示原样显示给用户。
 */
export async function deleteCategory(spaceId: string, categoryId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/categories/${categoryId}`, method: 'DELETE' });
}
