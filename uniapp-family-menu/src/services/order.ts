/**
 * 点单接口（对接自己的 FastAPI 后端）。
 *
 * 场景：家里来客人时点单——客人看菜单 → 选菜 → 提交，**无需付款**。
 * 所以这里刻意**没有价格、合计、结算、支付**：家庭做饭不是买卖。
 *
 * 写法和 services/fridge.ts 一致：
 *   1. 发请求交给 services/http.ts 统一处理（拼地址、带令牌、解析 { code, message, data }）；
 *   2. 下划线字段转驼峰只在这一个文件里做，页面不用关心后端命名习惯。
 *
 * 关于权限（**和菜单/冰箱刻意不同，值得记住**）：
 *   提交点单  —— 任何家庭成员都能做。点单是"提需求"，不是"改菜单"。
 *   管理点单  —— 只有**提交者本人**和**创建人**能改状态、删除。
 *   这个判断完全在后端，前端只看后端给的 canManage 字段决定按钮显不显示。
 *   前端自己算的话，规则一改就会出现"按钮看得到、点下去被拒"。
 *
 * ⚠️ 改状态用的是 PUT，不是 PATCH。
 *   微信小程序的 wx.request 官方 method 合法值里**有 PUT、没有 PATCH**。
 *   这里要改的本来也只是一个 status，用 PUT 语义上说得通，
 *   也就不必像菜谱那样再开一个行为相同的 POST 副本。
 */

import { request } from './http';

/** 待处理：刚提交，还没做 */
export const ORDER_STATUS_PENDING = 'pending';
/** 已完成：菜做好了 / 这单结束了 */
export const ORDER_STATUS_DONE = 'done';

/** 点单状态（目前只有两种，所以直接把两种字面量写成类型） */
export type OrderStatus = typeof ORDER_STATUS_PENDING | typeof ORDER_STATUS_DONE;

/** 后端返回的明细结构（原始字段） */
interface OrderItemDto {
  id: number;
  recipe_id: number | null;
  dish_name: string;
  spice: string | null;
  quantity: number;
}

/** 后端返回的点单结构（原始字段） */
interface OrderDto {
  id: number;
  space_id: number;
  created_by: number;
  created_by_nickname: string | null;
  guest_name: string | null;
  remark: string | null;
  status: string;
  created_at: string;
  can_manage: boolean;
  items: OrderItemDto[];
  dish_count: number;
  total_quantity: number;
}

/** 点单里的一道菜（前端使用，驼峰风格） */
export interface OrderItem {
  id: string;
  /**
   * 对应菜谱 ID。**菜谱被删后这里是空字符串**，但 dishName 仍然可用——
   * 明细里存了"下单那一刻的菜名快照"，所以历史单永远说得清当时点了什么。
   */
  recipeId: string;
  /** 菜名（下单时的快照） */
  dishName: string;
  /**
   * 辣度（下单时的快照）。没选辣度（那道菜本来就不问辣度）时为空字符串。
   *
   * 和菜名一样是**快照**：菜谱后来改了辣度档位，这张单仍然显示当时选的那档。
   */
  spice: string;
  quantity: number;
}

/** 一张点单 */
export interface DishOrder {
  id: string;
  spaceId: string;
  /** 提交者用户 ID */
  createdBy: number;
  /** 提交者昵称，后端查不到时为空字符串 */
  createdByName: string;
  /** 这单是谁点的（客人借手机时填客人名字），没填为空字符串 */
  guestName: string;
  /** 整单备注，没填为空字符串 */
  remark: string;
  status: OrderStatus;
  createdAt: string;
  /**
   * 当前登录者能不能管这张单（改状态 / 删除）。
   * 由后端判定——前端只管照着显示按钮，不要自己算。
   */
  canManage: boolean;
  items: OrderItem[];
  /** 一共几道菜（明细条数） */
  dishCount: number;
  /** 一共几份（各道菜份数之和） */
  totalQuantity: number;
}

/** 提交点单时要传的内容 */
export interface OrderInput {
  /** 这单是谁点的，可不填 */
  guestName: string;
  /** 整单备注，可不填 */
  remark: string;
  /** 点了哪几道菜 */
  items: Array<{ recipeId: string; quantity: number; spice: string }>;
}

/** 把后端的明细转成前端结构 */
function toItem(dto: OrderItemDto): OrderItem {
  return {
    id: String(dto.id),
    recipeId: dto.recipe_id === null || dto.recipe_id === undefined ? '' : String(dto.recipe_id),
    dishName: dto.dish_name,
    spice: dto.spice || '',
    quantity: dto.quantity,
  };
}

/** 把后端的点单转成前端结构，null 一律兜底成空字符串 */
function toOrder(dto: OrderDto): DishOrder {
  return {
    id: String(dto.id),
    spaceId: String(dto.space_id),
    createdBy: dto.created_by,
    createdByName: dto.created_by_nickname || '',
    guestName: dto.guest_name || '',
    remark: dto.remark || '',
    status: dto.status === ORDER_STATUS_DONE ? ORDER_STATUS_DONE : ORDER_STATUS_PENDING,
    createdAt: dto.created_at,
    canManage: Boolean(dto.can_manage),
    items: (Array.isArray(dto.items) ? dto.items : []).map(toItem),
    dishCount: dto.dish_count ?? 0,
    totalQuantity: dto.total_quantity ?? 0,
  };
}

/**
 * 拉取某个家庭组的点单，新的在前。
 *
 * @param status 只想要某一种状态时传 ORDER_STATUS_PENDING（"还没做的"），
 *               不传表示全部。筛选交给后端做，前端不用拿全量再自己筛。
 */
export async function fetchOrders(spaceId: string, status?: OrderStatus): Promise<DishOrder[]> {
  const qs = status ? `?status=${status}` : '';
  const list = await request<OrderDto[]>({ url: `/spaces/${spaceId}/orders${qs}` });
  return (Array.isArray(list) ? list : []).map(toOrder);
}

/** 提交一张点单。任何家庭成员都能提交 */
export async function createOrder(spaceId: string, input: OrderInput): Promise<DishOrder> {
  const dto = await request<OrderDto>({
    url: `/spaces/${spaceId}/orders`,
    method: 'POST',
    data: {
      // 显式传 null 而不是空串：后端把空串也归成"没填"，直接给 null 语义更清楚
      guest_name: input.guestName.trim() || null,
      remark: input.remark.trim() || null,
      items: input.items.map((item) => ({
        recipe_id: Number(item.recipeId),
        // 空字符串转 null：后端把"没选辣度"表达成 null，
        // 空串会被当成一个奇怪的辣度值（虽然也会被拒，但那是一条没必要的错误提示）
        spice: item.spice || null,
        quantity: item.quantity,
      })),
    },
  });
  return toOrder(dto);
}

/** 改点单状态（标记已完成 / 撤回成待处理）。权限：提交者本人或创建人 */
export async function updateOrderStatus(
  spaceId: string,
  orderId: string,
  status: OrderStatus,
): Promise<DishOrder> {
  const dto = await request<OrderDto>({
    url: `/spaces/${spaceId}/orders/${orderId}`,
    method: 'PUT',
    data: { status },
  });
  return toOrder(dto);
}

/** 删除一张点单（明细一起删）。权限：提交者本人或创建人 */
export async function deleteOrder(spaceId: string, orderId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/orders/${orderId}`, method: 'DELETE' });
}
