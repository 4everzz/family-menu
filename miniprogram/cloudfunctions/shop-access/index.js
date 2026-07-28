const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const DEFAULT_SHOP_ID = 'default-family-shop';
const DEFAULT_TABLE_ID = 'default-family-table';
const ROLE = {
  CUSTOMER: 'customer',
  STORE_ADMIN: 'store_admin',
  SUPER_ADMIN: 'super_admin',
};

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

function createEntryCode() {
  return crypto.randomBytes(4).toString('hex').toUpperCase();
}

function hashEntryCode(code) {
  return crypto.createHash('sha256').update(String(code)).digest('hex');
}

function createSessionToken() {
  return crypto.randomBytes(24).toString('hex');
}

function normalizeShopCode(value) {
  const code = String(value || '').trim().toUpperCase();
  return /^[A-Z0-9]{8}$/.test(code) ? code : '';
}

async function findUserByOpenId(openId) {
  const result = await db.collection('users').where({ openId, enabled: true }).limit(1).get();
  return result.data[0] || null;
}

async function requireSuperAdmin(openId) {
  const user = await findUserByOpenId(openId);
  return user && user.role === ROLE.SUPER_ADMIN ? user : null;
}

async function getAllDocuments(collectionName) {
  const pageSize = 100;
  const documents = [];
  for (let skip = 0; skip < 10000; skip += pageSize) {
    const result = await db.collection(collectionName).skip(skip).limit(pageSize).get();
    documents.push(...result.data);
    if (result.data.length < pageSize) break;
  }
  return documents;
}

async function ensureDefaultShop() {
  const existing = await db.collection('shops').doc(DEFAULT_SHOP_ID).get().catch(() => null);
  if (existing && existing.data) return { shop: existing.data, shopCode: '' };

  const shopCode = createEntryCode();
  const shop = {
    name: '家庭店',
    enabled: true,
    acceptingOrders: true,
    closedDates: [],
    orderEntryMode: 'store_entry',
    shopCodeHash: hashEntryCode(shopCode),
    displayShopCode: shopCode,
    shopCodeVersion: 1,
    menuVersion: 0,
    orderVersion: 0,
    memberVersion: 0,
    settingsVersion: 0,
    createdAt: db.serverDate(),
    updatedAt: db.serverDate(),
  };
  await db.collection('shops').doc(DEFAULT_SHOP_ID).set({ data: shop });
  return { shop, shopCode };
}

async function ensureDefaultTable() {
  const existing = await db.collection('shop_tables').doc(DEFAULT_TABLE_ID).get().catch(() => null);
  if (existing && existing.data) return { table: existing.data, tableCode: '' };

  const tableCode = createEntryCode();
  const table = {
    shopId: DEFAULT_SHOP_ID,
    name: '家庭桌',
    enabled: true,
    entryCodeHash: hashEntryCode(tableCode),
    displayCode: tableCode,
    entryCodeVersion: 1,
    sort: 0,
    createdAt: db.serverDate(),
    updatedAt: db.serverDate(),
  };
  await db.collection('shop_tables').doc(DEFAULT_TABLE_ID).set({ data: table });
  return { table, tableCode };
}

async function ensureDefaultMemberships(users) {
  let created = 0;
  let upgraded = 0;
  for (const user of users) {
    const role = user.role === 'manager' || user.role === ROLE.SUPER_ADMIN
      ? ROLE.STORE_ADMIN
      : ROLE.CUSTOMER;
    const existing = await db.collection('shop_members').where({
      shopId: DEFAULT_SHOP_ID,
      userId: user._id,
    }).limit(1).get();
    if (!existing.data.length) {
      await db.collection('shop_members').add({
        data: {
          shopId: DEFAULT_SHOP_ID,
          userId: user._id,
          role,
          enabled: user.enabled !== false,
          createdAt: db.serverDate(),
          updatedAt: db.serverDate(),
        },
      });
      created += 1;
      continue;
    }
    const member = existing.data[0];
    if (role === ROLE.STORE_ADMIN && member.role !== ROLE.STORE_ADMIN) {
      await db.collection('shop_members').doc(member._id).update({
        data: { role, enabled: user.enabled !== false, updatedAt: db.serverDate() },
      });
      upgraded += 1;
    }
  }
  return { created, upgraded };
}

async function attachDefaultShopId(collectionName) {
  const documents = await getAllDocuments(collectionName);
  const pending = documents.filter((item) => !item.shopId);
  for (const item of pending) {
    await db.collection(collectionName).doc(item._id).update({
      data: { shopId: DEFAULT_SHOP_ID, updatedAt: db.serverDate() },
    });
  }
  return pending.length;
}

async function migrateDefaultShop(openId) {
  const superAdmin = await requireSuperAdmin(openId);
  if (!superAdmin) return { ok: false, code: 'FORBIDDEN', message: '只有超级管理员可以执行数据迁移' };

  const [shopResult, tableResult, users] = await Promise.all([
    ensureDefaultShop(),
    ensureDefaultTable(),
    getAllDocuments('users'),
  ]);
  const memberships = await ensureDefaultMemberships(users);
  const [categories, dishes, orders] = await Promise.all([
    attachDefaultShopId('categories'),
    attachDefaultShopId('dishes'),
    attachDefaultShopId('orders'),
  ]);
  return {
    ok: true,
    migratedAt: getChinaDateKey(),
    shop: { id: DEFAULT_SHOP_ID, name: shopResult.shop.name, orderEntryMode: shopResult.shop.orderEntryMode },
    initialCodes: {
      shopCode: shopResult.shopCode,
      tableCode: tableResult.tableCode,
    },
    memberships,
    migrated: { categories, dishes, orders },
  };
}

async function listMyShops(openId) {
  const user = await findUserByOpenId(openId);
  if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
  const memberships = await db.collection('shop_members').where({ userId: user._id, enabled: true }).get();
  if (!memberships.data.length) return { ok: true, shops: [] };
  const shops = [];
  for (const member of memberships.data) {
    const result = await db.collection('shops').doc(member.shopId).get().catch(() => null);
    const shop = result && result.data;
    if (shop && shop.enabled !== false) {
      shops.push({
        id: shop._id,
        name: shop.name,
        role: member.role,
        orderEntryMode: shop.orderEntryMode,
        acceptingOrders: shop.acceptingOrders !== false,
        closedToday: Array.isArray(shop.closedDates) && shop.closedDates.includes(getChinaDateKey()),
      });
    }
  }
  return { ok: true, shops };
}

function isShopManagerRole(role) {
  return ['store_admin', 'store_owner', 'store_staff'].includes(String(role || ''));
}

async function getCurrentShopSnapshot(openId, event) {
  const user = await findUserByOpenId(openId);
  if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
  const shopId = String(event.shopId || '').trim();
  if (!shopId) return { ok: false, code: 'SHOP_REQUIRED', message: '请先进入店铺' };

  const shopResult = await db.collection('shops').doc(shopId).get().catch(() => null);
  const shop = shopResult && shopResult.data;
  if (!shop || shop.enabled === false) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在或已停用' };

  const memberResult = await db.collection('shop_members')
    .where({ shopId, userId: user._id, enabled: true }).limit(1).get();
  const member = memberResult.data[0] || null;
  const role = user.role === ROLE.SUPER_ADMIN ? ROLE.SUPER_ADMIN : (member ? member.role : ROLE.CUSTOMER);
  const isManager = user.role === ROLE.SUPER_ADMIN || isShopManagerRole(role);
  const entryToken = String(event.entryToken || '').trim();

  if (!isManager) {
    if (!entryToken) return { ok: false, code: 'ENTRY_SESSION_REQUIRED', message: '请扫描店铺码或桌码后进入' };
    const sessionResult = await db.collection('shop_entry_sessions').where({
      userId: user._id,
      shopId,
      tokenHash: hashEntryCode(entryToken),
    }).limit(1).get();
    const session = sessionResult.data[0];
    if (!session || new Date(session.expiresAt || 0).getTime() <= Date.now()) {
      return { ok: false, code: 'ENTRY_SESSION_EXPIRED', message: '本次点餐已失效，请重新扫描店铺二维码' };
    }
    if (session.tableId) {
      const tableResult = await db.collection('shop_tables').doc(session.tableId).get().catch(() => null);
      const table = tableResult && tableResult.data;
      if (!table || table.shopId !== shopId || table.enabled === false) {
        return { ok: false, code: 'TABLE_NOT_AVAILABLE', message: '当前桌位已失效，请重新扫描桌码' };
      }
    } else if (shop.orderEntryMode === 'table_required') {
      return { ok: false, code: 'TABLE_REQUIRED', message: '请扫描本店桌码后进入点餐' };
    }
  }

  return {
    ok: true,
    access: {
      role,
      isManager,
      versions: {
        menu: Number(shop.menuVersion) || 0,
        orders: Number(shop.orderVersion) || 0,
        members: Number(shop.memberVersion) || 0,
        settings: Number(shop.settingsVersion) || 0,
      },
    },
  };
}



async function rejoinShop(openId, event) {
  const user = await findUserByOpenId(openId);
  if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
  const shopId = String(event.shopId || '').trim();
  if (!shopId) return { ok: false, code: 'SHOP_REQUIRED', message: '请指定店铺' };
  const memberResult = await db.collection('shop_members').where({ shopId, userId: user._id, enabled: true }).limit(1).get();
  const member = memberResult.data[0];
  if (!member && user.role !== ROLE.SUPER_ADMIN) return { ok: false, code: 'NOT_MEMBER', message: '您尚未加入该店铺，请扫码后进入' };
  const shopResult = await db.collection('shops').doc(shopId).get().catch(() => null);
  const shop = shopResult && shopResult.data;
  if (!shop || shop.enabled === false) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺无效或已停用' };
  const session = await createEntrySession(user, shop, null);
  const role = user.role === ROLE.SUPER_ADMIN ? ROLE.SUPER_ADMIN : (member.role || ROLE.CUSTOMER);
  const isStaff = ['store_admin', 'store_owner', 'store_staff'].includes(role) || user.role === ROLE.SUPER_ADMIN;
  return {
    ok: true,
    shop: {
      id: shop._id,
      name: shop.name,
      role,
      orderEntryMode: shop.orderEntryMode,
      tableId: '',
      tableName: '',
      entryToken: isStaff ? '' : session.token,
      accessMode: isStaff ? 'staff' : 'customer',
    },
    expiresAt: session.expiresAt,
  };
}


async function createEntrySession(user, shop, table) {
  const token = createSessionToken();
  const expiresAt = new Date(Date.now() + 2 * 60 * 60 * 1000);
  await db.collection('shop_entry_sessions').where({ userId: user._id }).remove();
  await db.collection('shop_entry_sessions').add({
    data: {
      userId: user._id,
      shopId: shop._id,
      tableId: table ? table._id : '',
      tokenHash: hashEntryCode(token),
      expiresAt,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    },
  });
  return { token, expiresAt };
}

async function joinWithShopCode(openId, event) {
  const user = await findUserByOpenId(openId);
  if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
  const shopCode = normalizeShopCode(event.shopCode);
  if (!shopCode) return { ok: false, code: 'INVALID_SHOP_CODE', message: '请输入 8 位店铺码' };

  const codeHash = hashEntryCode(shopCode);
  const tableResult = await db.collection('shop_tables').where({ entryCodeHash: codeHash, enabled: true }).limit(1).get();
  const table = tableResult.data[0] || null;
  const shopResult = table
    ? await db.collection('shops').doc(table.shopId).get().catch(() => null)
    : await db.collection('shops').where({ shopCodeHash: codeHash }).limit(1).get();
  const shop = table ? (shopResult && shopResult.data) : shopResult.data[0];
  if (!shop || shop.enabled === false) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺码无效或店铺已停用' };
  if (shop.orderEntryMode === 'table_required' && !table) {
    return { ok: false, code: 'TABLE_REQUIRED', message: '请扫描本店桌码后进入点餐' };
  }
  const session = await createEntrySession(user, shop, table);
  return {
    ok: true,
    shop: {
      id: shop._id,
      name: shop.name,
      role: ROLE.CUSTOMER,
      orderEntryMode: shop.orderEntryMode,
      tableId: table ? table._id : '',
      tableName: table ? table.name : '',
      entryToken: session.token,
      accessMode: 'customer',
    },
    expiresAt: session.expiresAt,
  };
}

async function joinWithTableCode(openId, event) {
  const user = await findUserByOpenId(openId);
  if (!user) return { ok: false, code: 'UNAUTHORIZED', message: '请先登录' };
  const tableCode = normalizeShopCode(event.tableCode);
  if (!tableCode) return { ok: false, code: 'INVALID_TABLE_CODE', message: '请输入 8 位桌位码' };

  const codeHash = hashEntryCode(tableCode);
  const tableResult = await db.collection('shop_tables').where({ entryCodeHash: codeHash, enabled: true }).limit(1).get();
  const table = tableResult.data[0] || null;
  if (!table) return { ok: false, code: 'TABLE_NOT_FOUND', message: '桌位码无效或该桌位已停用' };
  const shopResult = await db.collection('shops').doc(table.shopId).get().catch(() => null);
  const shop = shopResult && shopResult.data;
  if (!shop || shop.enabled === false) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺已停用，暂时无法点餐' };

  const session = await createEntrySession(user, shop, table);
  return {
    ok: true,
    shop: {
      id: shop._id,
      name: shop.name,
      role: ROLE.CUSTOMER,
      orderEntryMode: shop.orderEntryMode,
      tableId: table._id,
      tableName: table.name,
      entryToken: session.token,
      accessMode: 'customer',
    },
    expiresAt: session.expiresAt,
  };
}

async function getMigrationStatus(openId) {
  const superAdmin = await requireSuperAdmin(openId);
  if (!superAdmin) return { ok: false, code: 'FORBIDDEN', message: '只有超级管理员可以查看迁移状态' };
  const shop = await db.collection('shops').doc(DEFAULT_SHOP_ID).get().catch(() => null);
  return { ok: true, migrated: !!(shop && shop.data) };
}

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  try {
    if (event.action === 'migrateDefaultShop') return await migrateDefaultShop(openId);
    if (event.action === 'listMyShops') return await listMyShops(openId);
    if (event.action === 'joinWithShopCode') return await joinWithShopCode(openId, event);
    if (event.action === 'joinWithTableCode') return await joinWithTableCode(openId, event);
    if (event.action === 'rejoinShop') return await rejoinShop(openId, event);
    if (event.action === 'getCurrentShopSnapshot') return await getCurrentShopSnapshot(openId, event);
    if (event.action === 'getMigrationStatus') return await getMigrationStatus(openId);
    return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
  } catch (error) {
    console.error('shop-access 执行失败', { action: event.action, message: error.message, stack: error.stack });
    return {
      ok: false,
      code: 'SHOP_ACCESS_ERROR',
      message: '店铺服务暂时不可用，请稍后重试',
      debugMessage: event.action === 'migrateDefaultShop' ? String(error.message || '未知云端错误') : '',
    };
  }
};
