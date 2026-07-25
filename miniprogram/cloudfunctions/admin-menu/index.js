const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const _ = db.command;
const SPICE_LEVELS = ['不辣', '微辣', '正常辣', '特辣'];

function normalizeImageFileId(value) {
  const imageFileId = String(value || '').trim();
  return imageFileId.startsWith('cloud://') ? imageFileId.slice(0, 512) : '';
}

function normalizeSpiceOptions(value) {
  const selected = Array.isArray(value) ? value.map((item) => String(item || '').trim()) : [];
  return SPICE_LEVELS.filter((level) => selected.includes(level));
}

function getDishSpiceConfig(dish, categories) {
  const spiceOptions = normalizeSpiceOptions(dish.spiceOptions);
  if (Array.isArray(dish.spiceOptions)) {
    const defaultSpice = spiceOptions.includes(dish.defaultSpice) ? dish.defaultSpice : (spiceOptions[0] || '');
    return { spiceOptions, defaultSpice };
  }
  const category = categories.find((item) => item.id === dish.category);
  const isSpicyCategory = category && (category.name === '川菜' || category.name === '湘菜');
  return isSpicyCategory ? { spiceOptions: SPICE_LEVELS, defaultSpice: '正常辣' } : { spiceOptions: [], defaultSpice: '' };
}

function applyDishSpiceConfig(dishes, categories) {
  return dishes.map((dish) => ({ ...dish, ...getDishSpiceConfig(dish, categories) }));
}

function normalizeDishOrderOptions(options, dish, categories) {
  const spiceConfig = getDishSpiceConfig(dish, categories);
  const requested = Array.isArray(options) ? options.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 6) : [];
  const nonSpiceOptions = requested.filter((item) => !SPICE_LEVELS.includes(item));
  if (!spiceConfig.spiceOptions.length) return nonSpiceOptions;
  const selectedSpice = requested.find((item) => spiceConfig.spiceOptions.includes(item)) || spiceConfig.defaultSpice;
  return selectedSpice ? [selectedSpice, ...nonSpiceOptions] : nonSpiceOptions;
}

function getChinaDateKey() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = parts.reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  return `${values.year}-${values.month}-${values.day}`;
}

function getChinaDayRange() {
  const [year, month, day] = getChinaDateKey().split('-').map(Number);
  const start = new Date(Date.UTC(year, month - 1, day) - 8 * 60 * 60 * 1000);
  return { start, end: new Date(start.getTime() + 24 * 60 * 60 * 1000) };
}

function hashEntryToken(token) {
  return crypto.createHash('sha256').update(String(token)).digest('hex');
}

async function getCurrentUser(openId) {
  const result = await db.collection('users').where({ openId, enabled: true }).limit(1).get();
  return result.data[0] || null;
}

function isManager(user) {
  return user && (user.role === 'manager' || user.role === 'super_admin');
}

async function getShopContext(user, event, requireStoreAdmin = false) {
  const shopId = String(event.shopId || '').trim();
  if (!shopId) {
    const error = new Error('请先通过店铺二维码进入点餐');
    error.code = 'SHOP_CONTEXT_REQUIRED';
    throw error;
  }
  const shopResult = await db.collection('shops').doc(shopId).get();
  const shop = shopResult.data;
  if (!shop || shop.enabled === false) {
    const error = new Error('店铺不存在或已停用');
    error.code = 'SHOP_NOT_AVAILABLE';
    throw error;
  }
  if (user.role === 'super_admin') return { shopId, shop, member: null };
  const memberResult = await db.collection('shop_members').where({ shopId, userId: user._id, enabled: true }).limit(1).get();
  const member = memberResult.data[0];
  if (!member) {
    const error = new Error('没有该店铺的访问权限');
    error.code = 'SHOP_ACCESS_DENIED';
    throw error;
  }
  if (requireStoreAdmin && member.role !== 'store_admin') {
    const error = new Error('没有该店铺的管理权限');
    error.code = 'SHOP_ADMIN_REQUIRED';
    throw error;
  }
  return { shopId, shop, member };
}

async function getCustomerShopContext(user, event) {
  const shopId = String(event.shopId || '').trim();
  const entryToken = String(event.entryToken || '').trim();
  if (!shopId) {
    const error = new Error('请扫描当前店铺二维码后点餐');
    error.code = 'ENTRY_SESSION_REQUIRED';
    throw error;
  }
  const shopResult = await db.collection('shops').doc(shopId).get();
  const shop = shopResult.data;
  if (!shop || shop.enabled === false) {
    const error = new Error('店铺不存在或已停用');
    error.code = 'SHOP_NOT_AVAILABLE';
    throw error;
  }
  const isViewAction = ['getCustomerMenu', 'listMyOrders', 'getMyOrder'].includes(event.action);
  if (entryToken) {
    const sessionResult = await db.collection('shop_entry_sessions').where({
      userId: user._id,
      shopId,
      tokenHash: hashEntryToken(entryToken),
    }).limit(1).get();
    const session = sessionResult.data[0];
    if (!session || new Date(session.expiresAt || 0).getTime() <= Date.now()) {
      if (isViewAction) {
        // 浏览操作：会话过期后降级为成员身份浏览，不强制扫码
        return { shopId, shop, table: null, session: null };
      }
      const error = new Error('本次点餐已失效，请重新扫描店铺二维码');
      error.code = 'ENTRY_SESSION_EXPIRED';
      throw error;
    }
    let table = null;
    if (session.tableId) {
      const tableResult = await db.collection('shop_tables').doc(session.tableId).get().catch(() => null);
      table = tableResult && tableResult.data;
      if (!table || table.shopId !== shopId || table.enabled === false) {
        if (isViewAction) {
          return { shopId, shop, table: null, session: null };
        }
        const error = new Error('当前桌位已失效，请重新扫描桌码');
        error.code = 'TABLE_NOT_AVAILABLE';
        throw error;
      }
    }
    if (shop.orderEntryMode === 'table_required' && !table) {
      if (isViewAction) {
        return { shopId, shop, table: null, session: null };
      }
      const error = new Error('请扫描本店桌码后下单');
      error.code = 'TABLE_REQUIRED';
      throw error;
    }
    return { shopId, shop, table, session };
  }
  // 没有会话令牌：仅浏览操作可通过店铺成员身份访问
  if (isViewAction) {
    return { shopId, shop, table: null, session: null };
  }
  const error = new Error('请先扫描店铺二维码后下单');
  error.code = 'ENTRY_SESSION_REQUIRED';
  throw error;
}

async function getAllDishes(shopId) {
  const pageSize = 100;
  const dishes = [];
  for (let skip = 0; skip < 1000; skip += pageSize) {
    const result = await db.collection('dishes').where({ shopId }).skip(skip).limit(pageSize).get();
    dishes.push(...result.data);
    if (result.data.length < pageSize) break;
  }
  return dishes.sort((left, right) => Number(left.id.slice(1)) - Number(right.id.slice(1)));
}

async function getAllCategories(shopId) {
  const result = await db.collection('categories').where({ shopId }).get();
  return result.data.sort((left, right) => {
    const leftSort = Number.isInteger(left.sort) ? left.sort : Number.MAX_SAFE_INTEGER;
    const rightSort = Number.isInteger(right.sort) ? right.sort : Number.MAX_SAFE_INTEGER;
    return leftSort - rightSort || left.name.localeCompare(right.name, 'zh-CN');
  });
}

async function initializeDishInventory(shopId) {
  const dishes = await getAllDishes(shopId);
  const updates = dishes.filter((dish) => (
    !Number.isInteger(dish.dailyStock)
    || !Number.isInteger(dish.stock)
    || typeof dish.manualSoldOut !== 'boolean'
  )).map((dish) => {
    const dailyStock = Number.isInteger(dish.dailyStock) && dish.dailyStock >= 0 ? dish.dailyStock : 10;
    const stock = Number.isInteger(dish.stock) && dish.stock >= 0 ? dish.stock : dailyStock;
    return db.collection('dishes').doc(dish._id).update({
      data: { dailyStock, stock: Math.min(stock, dailyStock), manualSoldOut: dish.manualSoldOut === true, updatedAt: db.serverDate() },
    });
  });
  await Promise.all(updates);
  return updates.length;
}

async function syncDailyInventory(shopId) {
  const dateKey = getChinaDateKey();
  const dishes = await getAllDishes(shopId);
  const updates = dishes.filter((dish) => dish.stockResetDate !== dateKey).map((dish) => {
    const dailyStock = Number.isInteger(dish.dailyStock) && dish.dailyStock >= 0 ? dish.dailyStock : 10;
    return db.collection('dishes').doc(dish._id).update({
      data: { dailyStock, stock: dailyStock, stockResetDate: dateKey, updatedAt: db.serverDate() },
    });
  });
  await Promise.all(updates);
  return { reset: updates.length, dateKey };
}

async function attachTemporaryImageUrls(dishes) {
  const fileIds = [...new Set(dishes.map((dish) => normalizeImageFileId(dish.imageFileId)).filter(Boolean))];
  if (!fileIds.length) return dishes.map((dish) => ({ ...dish, imageUrl: '' }));
  const result = await cloud.getTempFileURL({ fileList: fileIds });
  const imageUrls = new Map((result.fileList || [])
    .filter((item) => item.status === 0 && item.tempFileURL)
    .map((item) => [item.fileID, item.tempFileURL]));
  return dishes.map((dish) => ({
    ...dish,
    imageUrl: imageUrls.get(normalizeImageFileId(dish.imageFileId)) || '',
  }));
}

async function getCustomerMenu(shopId) {
  await syncDailyInventory(shopId);
  const [dishes, categories] = await Promise.all([getAllDishes(shopId), getAllCategories(shopId)]);
  const visibleDishes = applyDishSpiceConfig(dishes.filter((dish) => dish && dish.id && dish.name && dish.enabled !== false), categories);
  return { dishes: await attachTemporaryImageUrls(visibleDishes), categories };
}

async function createOrder(openId, ownerUserId, shopContext, event) {
  const requestedItems = Array.isArray(event.items) ? event.items : [];
  const remark = String(event.remark || '').trim().slice(0, 80);
  const table = shopContext.table || null;
  const mergedItems = requestedItems.reduce((result, item) => {
    const id = String(item.id || '');
    const quantity = Number(item.quantity);
    if (!id || !Number.isInteger(quantity) || quantity <= 0) return result;
    const existing = result.find((candidate) => candidate.id === id);
    if (existing) {
      existing.quantity += quantity;
    } else {
      result.push({ id, quantity, options: Array.isArray(item.options) ? item.options.slice(0, 6) : [] });
    }
    return result;
  }, []);
  if (!mergedItems.length) return { ok: false, code: 'EMPTY_ORDER', message: '请先选择菜品' };

  if (shopContext.shop.acceptingOrders === false || (shopContext.shop.closedDates || []).includes(getChinaDateKey())) {
    return { ok: false, code: 'SHOP_NOT_ACCEPTING', message: '店铺当前暂停接单' };
  }
  if (shopContext.shop.orderEntryMode === 'table_required') {
    if (!table) return { ok: false, code: 'INVALID_TABLE', message: '桌码无效，请重新扫描' };
  }
  const categories = await getAllCategories(shopContext.shopId);
  try {
    const order = await db.runTransaction(async (transaction) => {
      const dateKey = getChinaDateKey();
      const checkedItems = [];
      const unavailableNames = [];
      const outOfStockNames = [];
      for (const requestedItem of mergedItems) {
        const dishResult = await transaction.collection('dishes').where({ id: requestedItem.id, shopId: shopContext.shopId }).limit(1).get();
        const dish = dishResult.data[0];
        if (!dish || dish.enabled === false || dish.manualSoldOut === true) {
          unavailableNames.push(dish ? dish.name : '菜品');
          continue;
        }
        const dailyStock = Number.isInteger(dish.dailyStock) && dish.dailyStock >= 0 ? dish.dailyStock : 10;
        const stock = dish.stockResetDate === dateKey && Number.isInteger(dish.stock) && dish.stock >= 0
          ? dish.stock
          : dailyStock;
        if (stock < requestedItem.quantity) {
          outOfStockNames.push(dish.name);
          continue;
        }
        checkedItems.push({ dish, requestedItem: { ...requestedItem, options: normalizeDishOrderOptions(requestedItem.options, dish, categories) }, dailyStock, stock, dateKey });
      }
      if (unavailableNames.length) {
        const error = new Error('菜品已下架或售罄');
        error.code = 'UNAVAILABLE';
        error.dishNames = unavailableNames;
        throw error;
      }
      if (outOfStockNames.length) {
        const error = new Error('菜品库存不足');
        error.code = 'OUT_OF_STOCK';
        error.dishNames = outOfStockNames;
        throw error;
      }

      const orderItems = [];
      let total = 0;
      for (const { dish, requestedItem, dailyStock, stock, dateKey } of checkedItems) {
        await transaction.collection('dishes').doc(dish._id).update({
          data: { dailyStock, stock: stock - requestedItem.quantity, stockResetDate: dateKey, manualSoldOut: false, updatedAt: db.serverDate() },
        });
        const price = Number(dish.price);
        const item = {
          id: dish.id,
          name: dish.name,
          price,
          quantity: requestedItem.quantity,
          options: requestedItem.options,
          optionsText: requestedItem.options.join('、'),
          emoji: dish.emoji || '🍽',
          color: dish.color || '#D97706',
          imageFileId: dish.imageFileId || '',
        };
        orderItems.push(item);
        total += price * requestedItem.quantity;
      }
      const createdAt = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }).format(new Date());
      const order = {
        id: `HJ${Date.now().toString().slice(-8)}`,
        shopId: shopContext.shopId,
        tableId: table ? table._id : '',
        tableName: table ? table.name : '',
        orderChannel: table ? 'table' : 'store_entry',
        ownerUserId,
        ownerOpenId: openId,
        status: '制作中',
        statusNote: '订单已提交，正在制作中',
        total: total.toFixed(2),
        createdAt,
        items: orderItems,
        summary: orderItems.map((item) => `${item.name} × ${item.quantity}`).join('、'),
        remark,
        updatedAt: db.serverDate(),
        createdAtServer: db.serverDate(),
      };
      await transaction.collection('orders').add({ data: order });
      return order;
    });
    return { ok: true, order };
  } catch (error) {
    return {
      ok: false,
      code: error.code || 'CREATE_ORDER_FAILED',
      message: error.message || '提交订单失败',
      dishNames: error.dishNames || [],
    };
  }
}

async function listOrders(shopId) {
  const result = await db.collection('orders').where({ shopId }).orderBy('createdAtServer', 'desc').limit(100).get();
  return result.data;
}

async function getAllTodayOrders(shopId) {
  const { start, end } = getChinaDayRange();
  const orders = [];
  const pageSize = 100;
  for (let skip = 0; skip < 10000; skip += pageSize) {
    const result = await db.collection('orders').where({
      shopId,
      createdAtServer: _.gte(start).and(_.lt(end)),
    }).skip(skip).limit(pageSize).get();
    orders.push(...result.data);
    if (result.data.length < pageSize) break;
  }
  return orders;
}

async function getTodayDashboard(shopId) {
  await syncDailyInventory(shopId);
  const [orders, dishes] = await Promise.all([getAllTodayOrders(shopId), getAllDishes(shopId)]);
  const sales = new Map();
  let revenue = 0;
  let completedCount = 0;
  let makingCount = 0;

  orders.forEach((order) => {
    revenue += Number(order.total) || 0;
    if (order.status === '已完成') completedCount += 1;
    if (order.status === '制作中') makingCount += 1;
    (Array.isArray(order.items) ? order.items : []).forEach((item) => {
      const quantity = Number(item.quantity) || 0;
      if (quantity <= 0) return;
      const key = item.id || item.name;
      const current = sales.get(key) || { name: item.name || '未命名菜品', quantity: 0 };
      current.quantity += quantity;
      sales.set(key, current);
    });
  });

  const topDishes = [...sales.values()]
    .sort((left, right) => right.quantity - left.quantity || left.name.localeCompare(right.name, 'zh-CN'))
    .slice(0, 5);
  const soldOutCount = dishes.filter((dish) => dish.enabled !== false && (
    dish.manualSoldOut === true || (Number.isInteger(dish.stock) && dish.stock <= 0)
  )).length;

  return {
    dateKey: getChinaDateKey(),
    orderCount: orders.length,
    completedCount,
    makingCount,
    soldOutCount,
    revenue: Number(revenue.toFixed(2)),
    topDishes,
  };
}

async function listMyOrders(userId, openId, shopId) {
  const [ownedResult, legacyResult] = await Promise.all([
    db.collection('orders').where({ ownerUserId: userId, shopId }).orderBy('createdAtServer', 'desc').limit(100).get(),
    db.collection('orders').where({ ownerOpenId: openId, shopId }).orderBy('createdAtServer', 'desc').limit(100).get(),
  ]);
  const orders = [...ownedResult.data, ...legacyResult.data];
  return [...new Map(orders.map((item) => [item._id, item])).values()]
    .sort((left, right) => new Date(right.createdAtServer || 0).getTime() - new Date(left.createdAtServer || 0).getTime());
}

async function getMyOrder(id, userId, openId, shopId) {
  const ownedResult = await db.collection('orders').where({ id, ownerUserId: userId, shopId }).limit(1).get();
  if (ownedResult.data[0]) return ownedResult.data[0];
  const legacyResult = await db.collection('orders').where({ id, ownerOpenId: openId, shopId }).limit(1).get();
  return legacyResult.data[0] || null;
}

async function completeOrder(id, shopId) {
  const result = await db.collection('orders').where({ id, shopId, status: '制作中' }).update({
    data: {
      status: '已完成',
      statusNote: '订单已完成，感谢使用小家菜单',
      updatedAt: db.serverDate(),
    },
  });
  return result.stats.updated > 0;
}

async function deleteDish(id, shopId) {
  const dishResult = await db.collection('dishes').where({ id, shopId }).limit(1).get();
  const dish = dishResult.data[0];
  if (!dish) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };

  const imageFileId = normalizeImageFileId(dish.imageFileId);
  let isSharedImage = false;
  if (imageFileId) {
    const imageUsers = await db.collection('dishes').where({ imageFileId }).limit(2).get();
    isSharedImage = imageUsers.data.some((item) => item._id !== dish._id);
  }

  await db.collection('dishes').doc(dish._id).remove();
  if (imageFileId && !isSharedImage) {
    try {
      await cloud.deleteFile({ fileList: [imageFileId] });
    } catch (error) {
      // 菜品已删除，图片清理失败不影响历史订单与主流程。
    }
  }
  return { ok: true, id };
}

async function deleteCategory(id, shopId) {
  const categoryResult = await db.collection('categories').where({ id, shopId }).limit(1).get();
  const category = categoryResult.data[0];
  if (!category) return { ok: false, code: 'NOT_FOUND', message: '分类不存在' };

  const dishResult = await db.collection('dishes').where({ category: id, shopId }).limit(1).get();
  if (dishResult.data.length) {
    return { ok: false, code: 'CATEGORY_IN_USE', message: '该分类下仍有菜品，请先转移或删除菜品' };
  }

  await db.collection('categories').doc(category._id).remove();
  return { ok: true, id };
}

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  try {
    const user = await getCurrentUser(openId);
    if (event.action === 'getIdentity') return { ok: true, user: user ? { id: user._id, role: user.role } : null };
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    const customerActions = ['createOrder', 'syncDailyInventory', 'getCustomerMenu', 'listMyOrders', 'getMyOrder'];
    if (customerActions.includes(event.action)) {
      const shopContext = await getCustomerShopContext(user, event);
      if (event.action === 'createOrder') return createOrder(openId, user._id, shopContext, event);
      if (event.action === 'syncDailyInventory') return { ok: true, ...(await syncDailyInventory(shopContext.shopId)) };
      if (event.action === 'getCustomerMenu') return { ok: true, ...(await getCustomerMenu(shopContext.shopId)) };
      if (event.action === 'listMyOrders') return { ok: true, orders: await listMyOrders(user._id, openId, shopContext.shopId) };
      const id = String(event.id || '');
      const order = id ? await getMyOrder(id, user._id, openId, shopContext.shopId) : null;
      return order ? { ok: true, order } : { ok: false, code: 'NOT_FOUND', message: '订单不存在' };
    }
    const shopContext = await getShopContext(user, event, true);
    const shopId = shopContext.shopId;
    if (event.action === 'listAdminOrders') return { ok: true, orders: await listOrders(shopId) };
    if (event.action === 'getTodayDashboard') return { ok: true, dashboard: await getTodayDashboard(shopId) };
  if (event.action === 'completeOrder') {
    const id = String(event.id || '');
    if (!id) return { ok: false, code: 'INVALID_ORDER', message: '订单无效' };
    const completed = await completeOrder(id, shopId);
    return completed ? { ok: true } : { ok: false, code: 'ORDER_NOT_ACTIVE', message: '订单已完成或不存在' };
  }
  if (event.action === 'initializeDishInventory') return { ok: true, initialized: await initializeDishInventory(shopId) };
  if (event.action === 'listDishes') {
    const [dishes, categories] = await Promise.all([getAllDishes(shopId), getAllCategories(shopId)]);
    return { ok: true, dishes: applyDishSpiceConfig(dishes, categories) };
  }
  if (event.action === 'listCategories') return { ok: true, categories: await getAllCategories(shopId) };
  if (event.action === 'addCategory') {
    const name = String(event.name || '').trim();
    const sort = Number(event.sort);
    if (!name || !Number.isInteger(sort) || sort < 0) {
      return { ok: false, code: 'INVALID_CATEGORY', message: '分类名称或排序无效' };
    }
    const duplicate = await db.collection('categories').where({ shopId, name: name.slice(0, 12) }).limit(1).get();
    if (duplicate.data.length) return { ok: false, code: 'CATEGORY_EXISTS', message: '已有同名分类' };
    const category = {
      id: `c${Date.now()}`,
      shopId,
      name: name.slice(0, 12),
      sort,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    };
    await db.collection('categories').add({ data: category });
    return { ok: true, category };
  }
  if (event.action === 'updateCategory') {
    const id = String(event.id || '');
    const name = String(event.name || '').trim();
    const sort = Number(event.sort);
    if (!id || !name || !Number.isInteger(sort) || sort < 0) {
      return { ok: false, code: 'INVALID_CATEGORY', message: '分类名称或排序无效' };
    }
    const duplicate = await db.collection('categories').where({ shopId, name: name.slice(0, 12) }).limit(1).get();
    if (duplicate.data.some((item) => item.id !== id)) return { ok: false, code: 'CATEGORY_EXISTS', message: '已有同名分类' };
    const category = { name: name.slice(0, 12), sort };
    const result = await db.collection('categories').where({ id, shopId }).update({
      data: { ...category, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '分类不存在' };
    return { ok: true, category: { id, ...category } };
  }
  if (event.action === 'deleteCategory') {
    const id = String(event.id || '');
    if (!id) return { ok: false, code: 'INVALID_CATEGORY', message: '分类无效' };
    return deleteCategory(id, shopId);
  }
  if (event.action === 'updateDishPrice') {
    const id = String(event.id || '');
    const price = Number(event.price);
    if (!id || !Number.isFinite(price) || price <= 0) return { ok: false, code: 'INVALID_PRICE', message: '价格无效' };
    const result = await db.collection('dishes').where({ id, shopId }).update({
      data: { price, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, price };
  }
  if (event.action === 'updateDishEnabled') {
    const id = String(event.id || '');
    const enabled = event.enabled === true;
    if (!id) return { ok: false, code: 'INVALID_DISH', message: '菜品无效' };
    const result = await db.collection('dishes').where({ id, shopId }).update({
      data: { enabled, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, enabled };
  }
  if (event.action === 'updateDishManualSoldOut') {
    const id = String(event.id || '');
    const manualSoldOut = event.manualSoldOut === true;
    if (!id) return { ok: false, code: 'INVALID_DISH', message: '菜品无效' };
    const result = await db.collection('dishes').where({ id, shopId }).update({
      data: { manualSoldOut, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, manualSoldOut };
  }
  if (event.action === 'updateDishInventory') {
    const id = String(event.id || '');
    const dailyStock = Number(event.dailyStock);
    const stock = Number(event.stock);
    if (!id || !Number.isInteger(dailyStock) || !Number.isInteger(stock) || dailyStock < 0 || stock < 0 || stock > dailyStock) {
      return { ok: false, code: 'INVALID_STOCK', message: '库存数量无效' };
    }
    const result = await db.collection('dishes').where({ id, shopId }).update({
      data: { dailyStock, stock, stockResetDate: getChinaDateKey(), updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, dailyStock, stock };
  }
  if (event.action === 'updateDish') {
    const id = String(event.id || '');
    const name = String(event.name || '').trim();
    const category = String(event.category || '');
    const price = Number(event.price);
    const description = String(event.description || '').trim();
    const imageFileId = normalizeImageFileId(event.imageFileId);
    const spiceOptions = normalizeSpiceOptions(event.spiceOptions);
    const defaultSpice = spiceOptions.includes(event.defaultSpice) ? event.defaultSpice : (spiceOptions[0] || '');
    if (!id || !name || !category || !Number.isFinite(price) || price <= 0) {
      return { ok: false, code: 'INVALID_DISH', message: '菜品信息无效' };
    }
    const existingResult = await db.collection('dishes').where({ id, shopId }).limit(1).get();
    const existingDish = existingResult.data[0];
    if (!existingDish) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    const fallbackDailyStock = Number.isInteger(existingDish.dailyStock) && existingDish.dailyStock >= 0 ? existingDish.dailyStock : 10;
    const fallbackStock = Number.isInteger(existingDish.stock) && existingDish.stock >= 0 ? existingDish.stock : fallbackDailyStock;
    const enabled = typeof event.enabled === 'boolean' ? event.enabled : existingDish.enabled !== false;
    const manualSoldOut = typeof event.manualSoldOut === 'boolean' ? event.manualSoldOut : existingDish.manualSoldOut === true;
    const dailyStock = event.dailyStock === undefined ? fallbackDailyStock : Number(event.dailyStock);
    const stock = event.stock === undefined ? Math.min(fallbackStock, dailyStock) : Number(event.stock);
    if (!Number.isInteger(dailyStock) || !Number.isInteger(stock) || dailyStock < 0 || stock < 0 || stock > dailyStock) {
      return { ok: false, code: 'INVALID_STOCK', message: '库存数量无效' };
    }
    const categoryResult = await db.collection('categories').where({ id: category, shopId }).limit(1).get();
    if (!categoryResult.data.length) {
      return { ok: false, code: 'INVALID_CATEGORY', message: '分类不存在' };
    }
    const dish = {
      name: name.slice(0, 20),
      category,
      price,
      description: description.slice(0, 60),
      detail: description.slice(0, 60),
      imageFileId,
      spiceOptions,
      defaultSpice,
      enabled,
      manualSoldOut,
      dailyStock,
      stock,
      stockResetDate: getChinaDateKey(),
    };
    const result = await db.collection('dishes').where({ id, shopId }).update({
      data: { ...dish, updatedAt: db.serverDate() },
    });
    return { ok: true, dish: { id, ...dish } };
  }
  if (event.action === 'deleteDish') {
    const id = String(event.id || '');
    if (!id) return { ok: false, code: 'INVALID_DISH', message: '菜品无效' };
    return deleteDish(id, shopId);
  }
  if (event.action === 'addDish') {
    const name = String(event.name || '').trim();
    const category = String(event.category || '');
    const price = Number(event.price);
    const description = String(event.description || '').trim();
    const imageFileId = normalizeImageFileId(event.imageFileId);
    const spiceOptions = normalizeSpiceOptions(event.spiceOptions);
    const defaultSpice = spiceOptions.includes(event.defaultSpice) ? event.defaultSpice : (spiceOptions[0] || '');
    if (!name || !category || !Number.isFinite(price) || price <= 0) {
      return { ok: false, code: 'INVALID_DISH', message: '菜品信息无效' };
    }
    const categoryResult = await db.collection('categories').where({ id: category, shopId }).limit(1).get();
    if (!categoryResult.data.length) return { ok: false, code: 'INVALID_CATEGORY', message: '分类不存在' };
    const dish = {
      id: `d${Date.now()}`,
      shopId,
      category,
      name: name.slice(0, 20),
      price,
      description: (description || '新上菜品').slice(0, 60),
      detail: (description || '新上菜品').slice(0, 60),
      emoji: '菜',
      color: '#D97706',
      imageFileId,
      spiceOptions,
      defaultSpice,
      enabled: true,
      dailyStock: 10,
      stock: 10,
      manualSoldOut: false,
      stockResetDate: getChinaDateKey(),
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    };
    await db.collection('dishes').add({ data: dish });
    return { ok: true, dish };
  }
    return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
  } catch (error) {
    console.error('admin-menu 执行失败', { action: event.action, message: error.message, code: error.code });
    return {
      ok: false,
      code: error.code || 'ADMIN_MENU_ERROR',
      message: error.code ? error.message : '服务暂时不可用，请稍后重试',
    };
  }
};
