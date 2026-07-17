const cloud = require('wx-server-sdk');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();

async function isManager(openId) {
  try {
    const result = await db.collection('admins').where({ openId, enabled: true }).limit(1).get();
    return result.data.length > 0;
  } catch (error) {
    return false;
  }
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
  return result.data.sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
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

async function createOrder(openId, event) {
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

  try {
    const order = await db.runTransaction(async (transaction) => {
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
        const stock = Number.isInteger(dish.stock) && dish.stock >= 0 ? dish.stock : dailyStock;
        if (stock < requestedItem.quantity) {
          outOfStockNames.push(dish.name);
          continue;
        }
        checkedItems.push({ dish, requestedItem, dailyStock, stock });
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
      for (const { dish, requestedItem, dailyStock, stock } of checkedItems) {
        await transaction.collection('dishes').doc(dish._id).update({
          data: { dailyStock, stock: stock - requestedItem.quantity, manualSoldOut: false, updatedAt: db.serverDate() },
        });
        const price = Number(dish.price);
        const item = {
          id: dish.id,
          name: dish.name,
          price,
          quantity: requestedItem.quantity,
          options: requestedItem.options,
          optionsText: requestedItem.options.join('、'),
        };
        orderItems.push(item);
        total += price * requestedItem.quantity;
      }
      const createdAt = new Date().toLocaleString('zh-CN');
      const order = {
        id: `HJ${Date.now().toString().slice(-8)}`,
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

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  if (event.action === 'getIdentity') return { ok: true, openId };
  if (event.action === 'createOrder') return createOrder(openId, event);
  if (!(await isManager(openId))) return { ok: false, code: 'FORBIDDEN', message: '没有管理员权限' };
  if (event.action === 'initializeDishInventory') return { ok: true, initialized: await initializeDishInventory() };
  if (event.action === 'listDishes') return { ok: true, dishes: await getAllDishes() };
  if (event.action === 'listCategories') return { ok: true, categories: await getAllCategories() };
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
      data: { dailyStock, stock, updatedAt: db.serverDate() },
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
      enabled: true,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    };
    await db.collection('dishes').add({ data: dish });
    return { ok: true, dish };
  }
  return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
};
