const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const STORE_ADMIN = 'store_admin';
const VALID_ENTRY_MODES = ['store_entry', 'table_required'];

function createShopCode() {
  return crypto.randomBytes(4).toString('hex').toUpperCase();
}

function hashShopCode(code) {
  return crypto.createHash('sha256').update(String(code)).digest('hex');
}

async function getSuperAdmin(openId) {
  const result = await db.collection('users').where({ openId, enabled: true, role: 'super_admin' }).limit(1).get();
  return result.data[0] || null;
}

async function getCurrentUser(openId) {
  const result = await db.collection('users').where({ openId, enabled: true }).limit(1).get();
  return result.data[0] || null;
}

async function requireSuperAdmin(openId) {
  const user = await getSuperAdmin(openId);
  if (user) return user;
  const error = new Error('只有超级管理员可以管理店铺');
  error.code = 'FORBIDDEN';
  throw error;
}

async function createUniqueShopCode() {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const code = createShopCode();
    const result = await db.collection('shops').where({ shopCodeHash: hashShopCode(code) }).limit(1).get();
    if (!result.data.length) return code;
  }
  const error = new Error('店铺码生成失败，请重试');
  error.code = 'CODE_GENERATION_FAILED';
  throw error;
}

function makePublicShop(shop, member) {
  return {
    id: shop._id,
    name: shop.name,
    orderEntryMode: shop.orderEntryMode,
    acceptingOrders: shop.acceptingOrders !== false,
    enabled: shop.enabled !== false,
    role: member && member.role || STORE_ADMIN,
  };
}

async function listShops() {
  const result = await db.collection('shops').orderBy('createdAt', 'desc').limit(100).get();
  return result.data.map((shop) => makePublicShop(shop));
}

async function createShop(user, event) {
  const name = String(event.name || '').trim().slice(0, 20);
  const orderEntryMode = String(event.orderEntryMode || 'store_entry');
  if (!name || !VALID_ENTRY_MODES.includes(orderEntryMode)) {
    return { ok: false, code: 'INVALID_SHOP', message: '店铺名称或下单入口方式无效' };
  }
  const duplicate = await db.collection('shops').where({ name }).limit(1).get();
  if (duplicate.data.length) return { ok: false, code: 'SHOP_NAME_EXISTS', message: '已有同名店铺，请使用不同名称' };

  const shopCode = await createUniqueShopCode();
  const shop = {
    name,
    enabled: true,
    acceptingOrders: true,
    closedDates: [],
    orderEntryMode,
    shopCodeHash: hashShopCode(shopCode),
    shopCodeVersion: 1,
    createdBy: user._id,
    createdAt: db.serverDate(),
    updatedAt: db.serverDate(),
  };
  const created = await db.collection('shops').add({ data: shop });
  const shopId = created._id;
  await db.collection('shop_members').add({
    data: {
      shopId,
      userId: user._id,
      role: STORE_ADMIN,
      enabled: true,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    },
  });
  return {
    ok: true,
    shop: { id: shopId, name, orderEntryMode, role: STORE_ADMIN },
    initialShopCode: shopCode,
  };
}

function normalizeClosedDates(value) {
  const dates = Array.isArray(value) ? value : [];
  const uniqueDates = [...new Set(dates.map((item) => String(item || '').trim()))];
  const validDates = uniqueDates.filter((date) => {
    const match = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const checked = new Date(Date.UTC(year, month - 1, day));
    return checked.getUTCFullYear() === year && checked.getUTCMonth() === month - 1 && checked.getUTCDate() === day;
  });
  return validDates.sort().slice(0, 90);
}

async function requireShopAdmin(user, event) {
  const shopId = String(event.shopId || '').trim();
  if (!shopId) {
    const error = new Error('请先进入需要设置的店铺');
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
  if (user.role === 'super_admin') return { shopId, shop };
  const memberResult = await db.collection('shop_members').where({ shopId, userId: user._id, role: STORE_ADMIN, enabled: true }).limit(1).get();
  if (!memberResult.data[0]) {
    const error = new Error('没有该店铺的管理权限');
    error.code = 'SHOP_ADMIN_REQUIRED';
    throw error;
  }
  return { shopId, shop };
}

function makeShopSettings(shop) {
  return {
    id: shop._id,
    name: shop.name,
    acceptingOrders: shop.acceptingOrders !== false,
    closedDates: normalizeClosedDates(shop.closedDates),
    orderEntryMode: shop.orderEntryMode,
  };
}

async function updateOperatingRules(context, event) {
  const acceptingOrders = event.acceptingOrders === true;
  const closedDates = normalizeClosedDates(event.closedDates);
  await db.collection('shops').doc(context.shopId).update({
    data: { acceptingOrders, closedDates, updatedAt: db.serverDate() },
  });
  return { ok: true, settings: { ...makeShopSettings(context.shop), acceptingOrders, closedDates } };
}

async function rotateShopCode(context) {
  const shopCode = await createUniqueShopCode();
  await db.collection('shops').doc(context.shopId).update({
    data: {
      shopCodeHash: hashShopCode(shopCode),
      shopCodeVersion: Number(context.shop.shopCodeVersion || 0) + 1,
      updatedAt: db.serverDate(),
    },
  });
  return { ok: true, shopCode };
}

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  try {
    if (['listShops', 'createShop'].includes(event.action)) {
      const superAdmin = await requireSuperAdmin(openId);
      if (event.action === 'listShops') return { ok: true, shops: await listShops() };
      return createShop(superAdmin, event);
    }
    const user = await getCurrentUser(openId);
    if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
    const context = await requireShopAdmin(user, event);
    if (event.action === 'getShopSettings') return { ok: true, settings: makeShopSettings(context.shop) };
    if (event.action === 'updateOperatingRules') return updateOperatingRules(context, event);
    if (event.action === 'rotateShopCode') return rotateShopCode(context);
    return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
  } catch (error) {
    console.error('shop-admin 执行失败', { action: event.action, message: error.message, code: error.code });
    return {
      ok: false,
      code: error.code || 'SHOP_ADMIN_ERROR',
      message: error.code ? error.message : '店铺管理服务暂时不可用，请稍后重试',
    };
  }
};
