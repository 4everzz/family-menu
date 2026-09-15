/**
 * 点单用的本地购物车。
 *
 * 为什么不用 Pinia（状态库）？
 *   这个购物车是"选几道菜 → 提交 → 就清空"的临时状态，不需要跨模块共享、
 *   也不需要 devtools 调试，一个本地缓存加两个读写函数就够了。
 *   旧商家版的购物车用了 Pinia，那是跟着商家版一起删掉的依赖，没必要为这点状态加回来。
 *
 * 为什么要记住"这份购物车属于哪个家庭组"？
 *   一个人可能同时在"自己家"和"父母家"两个家庭组里。菜谱是按家庭组隔离的，
 *   如果把 A 家选的菜带到 B 家去提交，后端会直接拒绝（那几道菜不在 B 家的菜单里）。
 *   所以这里存下 spaceId，**只在家庭组对得上时才返回内容**——
 *   切换家庭后购物车会显示为空，切回来还在。
 *
 * 为什么同一道菜要按辣度分成两行？
 *   "两份微辣"和"一份微辣、一份特辣"完全是两回事，合并成一行会把口味弄丢。
 *   所以购物车行的身份是「菜谱 ID + 辣度」（见 cartKey），
 *   和旧小程序版用 cartKey 区分不同规格是同一个思路。
 */

/** 购物车里的一道菜 */
export interface CartItem {
  /** 菜谱 ID（字符串，和后端 ID 类型保持一致） */
  recipeId: string;
  /** 菜名，加入购物车时的快照，只用于本地显示 */
  dishName: string;
  /**
   * 选的辣度。
   * 空字符串表示这道菜本来就不问辣度（汤、饮品那类）。
   */
  spice: string;
  /** 份数 */
  quantity: number;
}

/** 本地缓存键 */
const CART_KEY = 'uni_family_dish_cart';

/**
 * 上限，**必须与后端保持一致**（见 backend/app/models/dish_order.py）。
 * 前端拦一道是为了给即时反馈；真正的保证在后端——接口是公开的。
 */
const MAX_ITEM_QUANTITY = 20;
const MAX_ORDER_ITEMS = 30;

/** 缓存里存的内容 */
interface StoredCart {
  /** 这份购物车属于哪个家庭组 */
  spaceId: string;
  items: CartItem[];
}

/**
 * 购物车行的唯一标识：**同一道菜 + 同一个辣度**才算同一行。
 *
 * 页面渲染列表时需要它做 key，内部查找也用它——
 * 两处用同一个函数算，就不会出现"显示的顺序和查找的顺序对不上"。
 */
export function cartKey(item: Pick<CartItem, 'recipeId' | 'spice'>): string {
  return `${item.recipeId}|${item.spice}`;
}

/** 读取原始缓存。内容损坏或没存过时返回 null */
function readRaw(): StoredCart | null {
  try {
    const raw = uni.getStorageSync(CART_KEY);
    if (!raw) return null;
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!parsed || typeof parsed.spaceId !== 'string' || !Array.isArray(parsed.items)) return null;
    return parsed as StoredCart;
  } catch (error) {
    // 缓存损坏按"购物车为空"处理，不让一个坏字符串把页面搞崩
    return null;
  }
}

/** 写回缓存 */
function write(cart: StoredCart): void {
  try {
    uni.setStorageSync(CART_KEY, JSON.stringify(cart));
  } catch (error) {
    // 本地写入失败不影响本次操作（调用方拿的是返回值），只是下次进来会丢
  }
}

/**
 * 读当前家庭组的购物车。
 * @param spaceId 当前家庭组 ID。与缓存里的家庭组对不上时返回空数组
 */
export function getCart(spaceId: string): CartItem[] {
  const stored = readRaw();
  if (!stored || !spaceId || stored.spaceId !== spaceId) return [];
  return stored.items;
}

/** 购物车里的总份数（用来显示底部购物车栏那个角标） */
export function cartCount(spaceId: string): number {
  return getCart(spaceId).reduce((sum, item) => sum + item.quantity, 0);
}

/**
 * 往购物车里加一道菜。
 *
 * 同一道菜 + 同一个辣度重复加就是**累加份数**；辣度不同则新开一行。
 * @returns 加完之后的完整列表
 * @throws 超出份数上限、或菜的道数超出上限时抛错（消息可直接展示给用户）
 */
export function addDish(
  spaceId: string,
  recipeId: string,
  dishName: string,
  spice = '',
): CartItem[] {
  const items = [...getCart(spaceId)];
  const key = cartKey({ recipeId, spice });
  const existing = items.find((item) => cartKey(item) === key);

  if (existing) {
    if (existing.quantity >= MAX_ITEM_QUANTITY) {
      throw new Error(`单道菜最多 ${MAX_ITEM_QUANTITY} 份`);
    }
    existing.quantity += 1;
  } else {
    if (items.length >= MAX_ORDER_ITEMS) {
      throw new Error(`一单最多点 ${MAX_ORDER_ITEMS} 道菜`);
    }
    items.push({ recipeId, dishName, spice, quantity: 1 });
  }

  write({ spaceId, items });
  return items;
}

/**
 * 直接设置某一行的份数。
 * 份数调到 0 或以下时等同于把这一行移出购物车——符合用户按"−"到底的预期。
 * @param key 用 cartKey(item) 算出来的行标识
 * @returns 改完之后的完整列表
 */
export function setQuantity(spaceId: string, key: string, quantity: number): CartItem[] {
  if (quantity > MAX_ITEM_QUANTITY) {
    throw new Error(`单道菜最多 ${MAX_ITEM_QUANTITY} 份`);
  }

  const items =
    quantity < 1
      ? getCart(spaceId).filter((item) => cartKey(item) !== key)
      : getCart(spaceId).map((item) => (cartKey(item) === key ? { ...item, quantity } : item));

  write({ spaceId, items });
  return items;
}

/**
 * 把某道菜的份数减 1。
 *
 * 这道菜可能在购物车里因为不同辣度而分成多行，
 * 减 1 时优先从「默认辣度」那一行扣（最符合用户"我只是少点一份"的直觉）；
 * 没有默认辣度行时，从第一行扣；扣到 0 就移除这一行。
 * @returns 改完之后的完整列表
 */
export function decreaseDish(
  spaceId: string,
  recipeId: string,
  defaultSpice = '',
): CartItem[] {
  const items = [...getCart(spaceId)];
  const matches = items.filter((item) => item.recipeId === recipeId);
  if (!matches.length) return items;

  const key = cartKey({ recipeId, spice: defaultSpice });
  const target =
    matches.find((item) => cartKey(item) === key && item.quantity > 0) ?? matches[0];
  const targetKey = cartKey(target);

  const updated = target.quantity <= 1
    ? items.filter((item) => cartKey(item) !== targetKey)
    : items.map((item) =>
        cartKey(item) === targetKey ? { ...item, quantity: item.quantity - 1 } : item,
      );

  write({ spaceId, items: updated });
  return updated;
}

/** 把一行移出购物车（数量减到 0 之外的显式删除） */
export function removeDish(spaceId: string, key: string): CartItem[] {
  const items = getCart(spaceId).filter((item) => cartKey(item) !== key);
  write({ spaceId, items });
  return items;
}

/**
 * 清空购物车。
 *
 * 提交成功后必须调用：否则用户会以为"刚才那单还没提交"，
 * 再点一次提交就变成下了两张一模一样的单。
 */
export function clearCart(): void {
  try {
    uni.removeStorageSync(CART_KEY);
  } catch (error) {
    // 忽略
  }
}
