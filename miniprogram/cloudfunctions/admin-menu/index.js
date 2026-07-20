const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
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

async function getCurrentUser(openId) {
  const result = await db.collection('users').where({ openId, enabled: true }).limit(1).get();
  return result.data[0] || null;
}

function isManager(user) {
  return user && (user.role === 'manager' || user.role === 'super_admin');
}

async function getAllDishes() {
  const pageSize = 100;
  const dishes = [];
  for (let skip = 0; skip < 1000; skip += pageSize) {
    const result = await db.collection('dishes').skip(skip).limit(pageSize).get();
    dishes.push(...result.data);
    if (result.data.length < pageSize) break;
  }
  return dishes.sort((left, right) => Number(left.id.slice(1)) - Number(right.id.slice(1)));
}

async function getAllCategories() {
  const result = await db.collection('categories').get();
  return result.data.sort((left, right) => {
    const leftSort = Number.isInteger(left.sort) ? left.sort : Number.MAX_SAFE_INTEGER;
    const rightSort = Number.isInteger(right.sort) ? right.sort : Number.MAX_SAFE_INTEGER;
    return leftSort - rightSort || left.name.localeCompare(right.name, 'zh-CN');
  });
}

async function initializeDishInventory() {
  const dishes = await getAllDishes();
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

async function syncDailyInventory() {
  const dateKey = getChinaDateKey();
  const dishes = await getAllDishes();
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

async function getCustomerMenu() {
  await syncDailyInventory();
  const [dishes, categories] = await Promise.all([getAllDishes(), getAllCategories()]);
  const visibleDishes = applyDishSpiceConfig(dishes.filter((dish) => dish && dish.id && dish.name && dish.enabled !== false), categories);
  return { dishes: await attachTemporaryImageUrls(visibleDishes), categories };
}

async function createOrder(openId, ownerUserId, event) {
  const requestedItems = Array.isArray(event.items) ? event.items : [];
  const remark = String(event.remark || '').trim().slice(0, 80);
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

  const categories = await getAllCategories();
  try {
    const order = await db.runTransaction(async (transaction) => {
      const dateKey = getChinaDateKey();
      const checkedItems = [];
      const unavailableNames = [];
      const outOfStockNames = [];
      for (const requestedItem of mergedItems) {
        const dishResult = await transaction.collection('dishes').where({ id: requestedItem.id }).limit(1).get();
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

async function listOrders(filter) {
  const collection = db.collection('orders');
  const query = Object.keys(filter).length ? collection.where(filter) : collection;
  const result = await query.orderBy('createdAtServer', 'desc').limit(100).get();
  return result.data;
}

async function listMyOrders(userId, openId) {
  const [ownedResult, legacyResult] = await Promise.all([
    db.collection('orders').where({ ownerUserId: userId }).orderBy('createdAtServer', 'desc').limit(100).get(),
    db.collection('orders').where({ ownerOpenId: openId }).orderBy('createdAtServer', 'desc').limit(100).get(),
  ]);
  const orders = [...ownedResult.data, ...legacyResult.data];
  return [...new Map(orders.map((item) => [item._id, item])).values()]
    .sort((left, right) => new Date(right.createdAtServer || 0).getTime() - new Date(left.createdAtServer || 0).getTime());
}

async function getMyOrder(id, userId, openId) {
  const ownedResult = await db.collection('orders').where({ id, ownerUserId: userId }).limit(1).get();
  if (ownedResult.data[0]) return ownedResult.data[0];
  const legacyResult = await db.collection('orders').where({ id, ownerOpenId: openId }).limit(1).get();
  return legacyResult.data[0] || null;
}

async function completeOrder(id) {
  const result = await db.collection('orders').where({ id, status: '制作中' }).update({
    data: {
      status: '已完成',
      statusNote: '订单已完成，感谢使用小家菜单',
      updatedAt: db.serverDate(),
    },
  });
  return result.stats.updated > 0;
}

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  const user = await getCurrentUser(openId);
  if (event.action === 'getIdentity') return { ok: true, user: user ? { id: user._id, role: user.role } : null };
  if (event.action === 'createOrder') {
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    return createOrder(openId, user._id, event);
  }
  if (event.action === 'syncDailyInventory') {
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    return { ok: true, ...(await syncDailyInventory()) };
  }
  if (event.action === 'getCustomerMenu') {
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    return { ok: true, ...(await getCustomerMenu()) };
  }
  if (event.action === 'listMyOrders') {
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    return { ok: true, orders: await listMyOrders(user._id, openId) };
  }
  if (event.action === 'getMyOrder') {
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    const id = String(event.id || '');
    const order = id ? await getMyOrder(id, user._id, openId) : null;
    return order ? { ok: true, order } : { ok: false, code: 'NOT_FOUND', message: '订单不存在' };
  }
  if (!isManager(user)) return { ok: false, code: 'FORBIDDEN', message: '没有管理员权限' };
  if (event.action === 'listAdminOrders') return { ok: true, orders: await listOrders({}) };
  if (event.action === 'completeOrder') {
    const id = String(event.id || '');
    if (!id) return { ok: false, code: 'INVALID_ORDER', message: '订单无效' };
    const completed = await completeOrder(id);
    return completed ? { ok: true } : { ok: false, code: 'ORDER_NOT_ACTIVE', message: '订单已完成或不存在' };
  }
  if (event.action === 'initializeDishInventory') return { ok: true, initialized: await initializeDishInventory() };
  if (event.action === 'listDishes') {
    const [dishes, categories] = await Promise.all([getAllDishes(), getAllCategories()]);
    return { ok: true, dishes: applyDishSpiceConfig(dishes, categories) };
  }
  if (event.action === 'listCategories') return { ok: true, categories: await getAllCategories() };
  if (event.action === 'addCategory') {
    const name = String(event.name || '').trim();
    const sort = Number(event.sort);
    if (!name || !Number.isInteger(sort) || sort < 0) {
      return { ok: false, code: 'INVALID_CATEGORY', message: '分类名称或排序无效' };
    }
    const duplicate = await db.collection('categories').where({ name: name.slice(0, 12) }).limit(1).get();
    if (duplicate.data.length) return { ok: false, code: 'CATEGORY_EXISTS', message: '已有同名分类' };
    const category = {
      id: `c${Date.now()}`,
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
    const duplicate = await db.collection('categories').where({ name: name.slice(0, 12) }).limit(1).get();
    if (duplicate.data.some((item) => item.id !== id)) return { ok: false, code: 'CATEGORY_EXISTS', message: '已有同名分类' };
    const category = { name: name.slice(0, 12), sort };
    const result = await db.collection('categories').where({ id }).update({
      data: { ...category, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '分类不存在' };
    return { ok: true, category: { id, ...category } };
  }
  if (event.action === 'updateDishPrice') {
    const id = String(event.id || '');
    const price = Number(event.price);
    if (!id || !Number.isFinite(price) || price <= 0) return { ok: false, code: 'INVALID_PRICE', message: '价格无效' };
    const result = await db.collection('dishes').where({ id }).update({
      data: { price, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, price };
  }
  if (event.action === 'updateDishEnabled') {
    const id = String(event.id || '');
    const enabled = event.enabled === true;
    if (!id) return { ok: false, code: 'INVALID_DISH', message: '菜品无效' };
    const result = await db.collection('dishes').where({ id }).update({
      data: { enabled, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, enabled };
  }
  if (event.action === 'updateDishManualSoldOut') {
    const id = String(event.id || '');
    const manualSoldOut = event.manualSoldOut === true;
    if (!id) return { ok: false, code: 'INVALID_DISH', message: '菜品无效' };
    const result = await db.collection('dishes').where({ id }).update({
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
    const result = await db.collection('dishes').where({ id }).update({
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
    const categoryResult = await db.collection('categories').where({ id: category }).limit(1).get();
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
    };
    const result = await db.collection('dishes').where({ id }).update({
      data: { ...dish, updatedAt: db.serverDate() },
    });
    if (!result.stats.updated) return { ok: false, code: 'NOT_FOUND', message: '菜品不存在' };
    return { ok: true, dish: { id, ...dish } };
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
    const categoryResult = await db.collection('categories').where({ id: category }).limit(1).get();
    if (!categoryResult.data.length) return { ok: false, code: 'INVALID_CATEGORY', message: '分类不存在' };
    const dish = {
      id: `d${Date.now()}`,
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
};
