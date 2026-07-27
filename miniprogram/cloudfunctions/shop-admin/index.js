const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const STORE_ADMIN = 'store_admin';
const STORE_OWNER = 'store_owner';
const STORE_STAFF = 'store_staff';
const SHOP_MANAGER_ROLES = [STORE_ADMIN, STORE_OWNER, STORE_STAFF];
const VALID_ENTRY_MODES = ['store_entry', 'table_required'];
const SYSTEM_ID_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const SYSTEM_ID_LENGTH = 8;

function normalizeAvatarFileId(value) {
  const avatarFileId = String(value || '').trim();
  return avatarFileId.startsWith('cloud://') ? avatarFileId.slice(0, 512) : '';
}

function createShopCode() {
  return crypto.randomBytes(4).toString('hex').toUpperCase();
}

function createSystemId() {
  const bytes = crypto.randomBytes(SYSTEM_ID_LENGTH);
  let value = '';
  for (let index = 0; index < SYSTEM_ID_LENGTH; index += 1) {
    value += SYSTEM_ID_CHARS[bytes[index] % SYSTEM_ID_CHARS.length];
  }
  return value;
}

async function createUniqueSystemId() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const systemId = createSystemId();
    const result = await db.collection('users').where({ systemId }).limit(1).get();
    if (!result.data.length) return systemId;
  }
  const error = new Error('用户ID生成失败，请重试');
  error.code = 'SYSTEM_ID_GENERATION_FAILED';
  throw error;
}

async function ensureUserSystemId(user) {
  if (!user || user.systemId) return user;
  const systemId = await createUniqueSystemId();
  await db.collection('users').doc(user._id).update({
    data: { systemId, updatedAt: db.serverDate() },
  });
  return { ...user, systemId };
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
  const user = result.data[0] || null;
  return user ? ensureUserSystemId(user) : null;
}

async function requireSuperAdmin(openId) {
  const user = await getSuperAdmin(openId);
  if (user) return user;
  const error = new Error('只有超级管理员可以管理店铺');
  error.code = 'FORBIDDEN';
  throw error;
}

async function createUniqueEntryCode() {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const code = createShopCode();
    const codeHash = hashShopCode(code);
    const [shopResult, tableResult] = await Promise.all([
      db.collection('shops').where({ shopCodeHash: codeHash }).limit(1).get(),
      db.collection('shop_tables').where({ entryCodeHash: codeHash }).limit(1).get(),
    ]);
    if (!shopResult.data.length && !tableResult.data.length) return code;
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
    role: normalizeMemberRole(member && member.role || STORE_OWNER),
  };
}

function normalizeMemberRole(role) {
  const value = String(role || '');
  if (value === STORE_ADMIN) return STORE_OWNER;
  if (value === STORE_OWNER || value === STORE_STAFF) return value;
  return 'customer';
}

function isStoreOwnerRole(role) {
  const value = String(role || '');
  return value === STORE_ADMIN || value === STORE_OWNER;
}

function canManageShopMembers(context) {
  return context.isSuperAdmin || isStoreOwnerRole(context.member && context.member.role);
}

function makePublicUser(user) {
  return {
    id: user._id,
    systemId: user.systemId || '',
    nickname: user.nickname || '微信用户',
    avatarFileId: normalizeAvatarFileId(user.avatarFileId),
    role: user.role || 'user',
    enabled: user.enabled !== false,
  };
}

function makePublicShopMember(member, user) {
  const role = normalizeMemberRole(member.role);
  return {
    id: member._id,
    userId: member.userId,
    systemId: user && user.systemId ? user.systemId : '',
    nickname: user && user.nickname ? user.nickname : '微信用户',
    avatarFileId: user ? normalizeAvatarFileId(user.avatarFileId) : '',
    userEnabled: user ? user.enabled !== false : false,
    role,
    roleText: role === STORE_OWNER ? '一级管理员' : '二级管理员',
    enabled: member.enabled !== false,
  };
}

async function attachAvatarUrls(items) {
  const fileIds = [...new Set(items.map((item) => normalizeAvatarFileId(item.avatarFileId)).filter(Boolean))];
  if (!fileIds.length) return items.map((item) => ({ ...item, avatarUrl: '' }));
  try {
    const result = await cloud.getTempFileURL({ fileList: fileIds });
    const avatarUrls = new Map((result.fileList || [])
      .filter((item) => item.status === 0 && item.tempFileURL)
      .map((item) => [item.fileID, item.tempFileURL]));
    return items.map((item) => ({
      ...item,
      avatarUrl: avatarUrls.get(normalizeAvatarFileId(item.avatarFileId)) || '',
    }));
  } catch (error) {
    return items.map((item) => ({ ...item, avatarUrl: '' }));
  }
}

async function listShops() {
  const result = await db.collection('shops').orderBy('createdAt', 'desc').limit(100).get();
  return result.data.map((shop) => makePublicShop(shop));
}

async function createShop(user, event) {
  const name = String(event.name || '').trim().slice(0, 20);
  const orderEntryMode = 'store_entry';
  if (!name) return { ok: false, code: 'INVALID_SHOP', message: '店铺名称无效' };
  const duplicate = await db.collection('shops').where({ name }).limit(1).get();
  if (duplicate.data.length) return { ok: false, code: 'SHOP_NAME_EXISTS', message: '已有同名店铺，请使用不同名称' };

  const shopCode = await createUniqueEntryCode();
  const shop = {
    name,
    enabled: true,
    acceptingOrders: true,
    closedDates: [],
    orderEntryMode,
    shopCodeHash: hashShopCode(shopCode),
    displayShopCode: shopCode,
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
      role: STORE_OWNER,
      enabled: true,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    },
  });
  return {
    ok: true,
    shop: { id: shopId, name, orderEntryMode, role: STORE_OWNER },
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
  if (user.role === 'super_admin') return { shopId, shop, member: null, user, isSuperAdmin: true };
  const memberResult = await db.collection('shop_members').where({ shopId, userId: user._id, enabled: true }).limit(1).get();
  const member = memberResult.data[0];
  if (!member || !SHOP_MANAGER_ROLES.includes(member.role)) {
    const error = new Error('没有该店铺的管理权限');
    error.code = 'SHOP_ADMIN_REQUIRED';
    throw error;
  }
  return { shopId, shop, member, user, isSuperAdmin: false };
}

function makeShopSettings(shop) {
  return {
    id: shop._id,
    name: shop.name,
    displayShopCode: String(shop.displayShopCode || ''),
    acceptingOrders: shop.acceptingOrders !== false,
    closedDates: normalizeClosedDates(shop.closedDates),
    orderEntryMode: VALID_ENTRY_MODES.includes(shop.orderEntryMode) ? shop.orderEntryMode : 'store_entry',
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

async function updateOrderEntryMode(context, event) {
  const orderEntryMode = String(event.orderEntryMode || '').trim();
  if (!VALID_ENTRY_MODES.includes(orderEntryMode)) {
    return { ok: false, code: 'INVALID_ENTRY_MODE', message: '下单入口方式无效' };
  }
  if (orderEntryMode === 'table_required') {
    const activeTable = await db.collection('shop_tables')
      .where({ shopId: context.shopId, enabled: true })
      .limit(1)
      .get();
    if (!activeTable.data.length) {
      return {
        ok: false,
        code: 'ACTIVE_TABLE_REQUIRED',
        message: '请先新增并启用至少一张堂食桌位',
      };
    }
  }
  await db.collection('shops').doc(context.shopId).update({
    data: { orderEntryMode, updatedAt: db.serverDate() },
  });
  return { ok: true, settings: { ...makeShopSettings(context.shop), orderEntryMode } };
}

async function rotateShopCode(context) {
  const shopCode = await createUniqueEntryCode();
  await db.collection('shops').doc(context.shopId).update({
    data: {
      shopCodeHash: hashShopCode(shopCode),
      displayShopCode: shopCode,
      shopCodeVersion: Number(context.shop.shopCodeVersion || 0) + 1,
      updatedAt: db.serverDate(),
    },
  });
  return { ok: true, shopCode };
}

function makePublicTable(table) {
  return {
    id: table._id,
    name: table.name,
    enabled: table.enabled !== false,
    displayCode: String(table.displayCode || ''),
    sort: Number.isInteger(table.sort) ? table.sort : 0,
  };
}

async function listTables(context) {
  const result = await db.collection('shop_tables').where({ shopId: context.shopId }).limit(100).get();
  return result.data
    .map(makePublicTable)
    .sort((left, right) => left.sort - right.sort || left.name.localeCompare(right.name, 'zh-CN'));
}

async function getTableInShop(context, id) {
  const tableId = String(id || '').trim();
  if (!tableId) return null;
  const result = await db.collection('shop_tables').doc(tableId).get().catch(() => null);
  const table = result && result.data;
  return table && table.shopId === context.shopId ? table : null;
}

async function addTable(context, event) {
  const name = String(event.name || '').trim().slice(0, 16);
  if (!name) return { ok: false, code: 'INVALID_TABLE', message: '请输入桌位名称' };
  const duplicate = await db.collection('shop_tables').where({ shopId: context.shopId, name }).limit(1).get();
  if (duplicate.data.length) return { ok: false, code: 'TABLE_EXISTS', message: '已有同名桌位' };
  const tableCode = await createUniqueEntryCode();
  const sort = Date.now();
  const created = await db.collection('shop_tables').add({
    data: {
      shopId: context.shopId,
      name,
      enabled: true,
      entryCodeHash: hashShopCode(tableCode),
      displayCode: tableCode,
      entryCodeVersion: 1,
      sort,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    },
  });
  return { ok: true, table: { id: created._id, name, enabled: true, displayCode: tableCode, sort }, tableCode };
}

async function updateTableEnabled(context, event) {
  const tableId = String(event.id || '').trim();
  if (!tableId) return { ok: false, code: 'NOT_FOUND', message: '桌位不存在' };
  const enabled = event.enabled === true;
  const result = await db.runTransaction(async (transaction) => {
    const [shopResult, tableResult] = await Promise.all([
      transaction.collection('shops').doc(context.shopId).get(),
      transaction.collection('shop_tables').doc(tableId).get(),
    ]);
    const shop = shopResult.data;
    const table = tableResult.data;
    if (!shop || shop.enabled === false || !table || table.shopId !== context.shopId) {
      return { ok: false, code: 'NOT_FOUND', message: '桌位不存在' };
    }
    if (shop.orderEntryMode === 'table_required' && table.enabled !== false && !enabled) {
      const activeTables = await transaction.collection('shop_tables')
        .where({ shopId: context.shopId, enabled: true })
        .limit(2)
        .get();
      if (activeTables.data.length <= 1) {
        return {
          ok: false,
          code: 'ACTIVE_TABLE_REQUIRED',
          message: '桌码模式至少需要保留一张可使用桌位',
        };
      }
    }
    await transaction.collection('shop_tables').doc(table._id).update({
      data: { enabled, updatedAt: db.serverDate() },
    });
    return { ok: true, table: { ...makePublicTable(table), enabled } };
  });
  return result;
}

async function rotateTableCode(context, event) {
  const table = await getTableInShop(context, event.id);
  if (!table) return { ok: false, code: 'NOT_FOUND', message: '桌位不存在' };
  const tableCode = await createUniqueEntryCode();
  await db.collection('shop_tables').doc(table._id).update({
    data: {
      entryCodeHash: hashShopCode(tableCode),
      displayCode: tableCode,
      entryCodeVersion: Number(table.entryCodeVersion || 0) + 1,
      updatedAt: db.serverDate(),
    },
  });
  return { ok: true, table: makePublicTable(table), tableCode };
}

async function getUserMap(userIds) {
  const uniqueIds = [...new Set(userIds.filter(Boolean))];
  const pairs = await Promise.all(uniqueIds.map(async (id) => {
    const result = await db.collection('users').doc(id).get().catch(() => null);
    return [id, result && result.data ? await ensureUserSystemId(result.data) : null];
  }));
  return new Map(pairs);
}

async function listShopMembers(context) {
  if (!canManageShopMembers(context)) {
    return { ok: false, code: 'MEMBER_MANAGER_REQUIRED', message: '只有一级管理员可以管理店铺成员' };
  }
  const result = await db.collection('shop_members').where({ shopId: context.shopId }).limit(100).get();
  const members = result.data.filter((member) => member.enabled !== false && SHOP_MANAGER_ROLES.includes(member.role));
  const userMap = await getUserMap(members.map((member) => member.userId));
  const roleOrder = { store_admin: 0, store_owner: 0, store_staff: 1 };
  const publicMembers = await attachAvatarUrls(members
    .map((member) => makePublicShopMember(member, userMap.get(member.userId)))
    .sort((left, right) => (roleOrder[left.role] || 9) - (roleOrder[right.role] || 9) || left.nickname.localeCompare(right.nickname, 'zh-CN')));
  return {
    ok: true,
    canGrantOwner: context.isSuperAdmin === true,
    members: publicMembers,
  };
}

function escapeRegExp(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeSearchText(value) {
  return String(value || '').trim().replace(/["'“”‘’\s]/g, '').toLowerCase();
}

async function searchUsers(context, event) {
  if (!canManageShopMembers(context)) {
    return { ok: false, code: 'MEMBER_MANAGER_REQUIRED', message: '只有一级管理员可以管理店铺成员' };
  }
  const keyword = String(event.keyword || '').trim();
  const normalizedKeyword = normalizeSearchText(keyword);
  if (!keyword) return { ok: true, users: [] };
  const exactSystemId = normalizedKeyword.toUpperCase();
  const userResult = await db.collection('users').where({
    nickname: db.RegExp({ regexp: escapeRegExp(keyword), options: 'i' }),
    enabled: true,
  }).limit(20).get();
  const systemIdResult = /^[A-Z0-9]{6,8}$/.test(exactSystemId)
    ? await db.collection('users').where({
      systemId: db.RegExp({ regexp: `^${escapeRegExp(exactSystemId)}$`, options: 'i' }),
      enabled: true,
    }).limit(20).get()
    : { data: [] };
  const exactResult = /^[a-zA-Z0-9_-]{8,}$/.test(keyword)
    ? await db.collection('users').doc(keyword).get().catch(() => null)
    : null;
  const users = await Promise.all([...userResult.data, ...systemIdResult.data].map((user) => ensureUserSystemId(user)));
  if (exactResult && exactResult.data) {
    users.unshift(await ensureUserSystemId(exactResult.data));
  }
  if (context.isSuperAdmin && context.user) {
    const selfName = normalizeSearchText(context.user.nickname);
    const selfId = normalizeSearchText(context.user._id);
    const selfSystemId = normalizeSearchText(context.user.systemId);
    const keywordMatchesSelf = (selfName && (selfName.includes(normalizedKeyword) || normalizedKeyword.includes(selfName)))
      || (selfId && selfId.includes(normalizedKeyword))
      || (selfSystemId && (selfSystemId.includes(normalizedKeyword) || normalizedKeyword.includes(selfSystemId)));
    if (keywordMatchesSelf && !users.some((user) => user._id === context.user._id)) {
      users.unshift(context.user);
    }
  }
  const memberResult = await db.collection('shop_members').where({ shopId: context.shopId }).limit(100).get();
  const memberByUserId = new Map(memberResult.data.map((member) => [member.userId, member]));
  const publicUsers = users
    .filter((user) => context.isSuperAdmin || user.role !== 'super_admin')
    .filter((user, index, self) => self.findIndex((item) => item._id === user._id) === index)
    .slice(0, 20)
    .map((user) => {
      const member = memberByUserId.get(user._id);
      return {
        ...makePublicUser(user),
        memberRole: member && member.enabled !== false ? normalizeMemberRole(member.role) : '',
        memberRoleText: member && member.enabled !== false
          ? (normalizeMemberRole(member.role) === STORE_OWNER ? '一级管理员' : '二级管理员')
          : '未授权',
      };
    });
  return {
    ok: true,
    users: await attachAvatarUrls(publicUsers),
  };
}

async function grantShopMember(context, event) {
  if (!canManageShopMembers(context)) {
    return { ok: false, code: 'MEMBER_MANAGER_REQUIRED', message: '只有一级管理员可以管理店铺成员' };
  }
  const userId = String(event.userId || '').trim();
  const role = String(event.role || '').trim();
  if (!userId || ![STORE_OWNER, STORE_STAFF].includes(role)) {
    return { ok: false, code: 'INVALID_MEMBER', message: '成员或权限无效' };
  }
  if (role === STORE_OWNER && !context.isSuperAdmin) {
    return { ok: false, code: 'OWNER_GRANT_FORBIDDEN', message: '只有超级管理员可以设置一级管理员' };
  }
  const targetResult = await db.collection('users').doc(userId).get().catch(() => null);
  const target = targetResult && targetResult.data ? await ensureUserSystemId(targetResult.data) : null;
  if (!target || target.enabled === false || (target.role === 'super_admin' && !context.isSuperAdmin)) {
    return { ok: false, code: 'INVALID_USER', message: '用户不存在或不可授权' };
  }
  const existingResult = await db.collection('shop_members').where({ shopId: context.shopId, userId }).limit(1).get();
  const existing = existingResult.data[0];
  if (existing) {
    await db.collection('shop_members').doc(existing._id).update({
      data: {
        role,
        enabled: true,
        updatedAt: db.serverDate(),
        updatedBy: context.isSuperAdmin ? 'super_admin' : context.member.userId,
      },
    });
    return { ok: true, member: makePublicShopMember({ ...existing, role, enabled: true }, target) };
  }
  const created = await db.collection('shop_members').add({
    data: {
      shopId: context.shopId,
      userId,
      role,
      enabled: true,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
      createdBy: context.isSuperAdmin ? 'super_admin' : context.member.userId,
    },
  });
  return { ok: true, member: makePublicShopMember({ _id: created._id, shopId: context.shopId, userId, role, enabled: true }, target) };
}

async function grantSelfOwner(context) {
  if (!context.isSuperAdmin || !context.user) {
    return { ok: false, code: 'SUPER_ADMIN_REQUIRED', message: '只有超级管理员可以执行此操作' };
  }
  return grantShopMember(context, { userId: context.user._id, role: STORE_OWNER });
}

async function revokeShopMember(context, event) {
  if (!canManageShopMembers(context)) {
    return { ok: false, code: 'MEMBER_MANAGER_REQUIRED', message: '只有一级管理员可以管理店铺成员' };
  }
  const userId = String(event.userId || '').trim();
  if (!userId) return { ok: false, code: 'INVALID_MEMBER', message: '成员无效' };
  if (!context.isSuperAdmin && context.member && context.member.userId === userId) {
    return { ok: false, code: 'SELF_REVOKE_FORBIDDEN', message: '不能撤销自己的店铺权限' };
  }
  const result = await db.collection('shop_members').where({ shopId: context.shopId, userId }).limit(1).get();
  const member = result.data[0];
  if (!member || !SHOP_MANAGER_ROLES.includes(member.role)) {
    return { ok: false, code: 'NOT_FOUND', message: '成员不存在' };
  }
  if (isStoreOwnerRole(member.role) && !context.isSuperAdmin) {
    return { ok: false, code: 'OWNER_REVOKE_FORBIDDEN', message: '只有超级管理员可以撤销一级管理员' };
  }
  await db.collection('shop_members').doc(member._id).update({
    data: {
      enabled: false,
      updatedAt: db.serverDate(),
      updatedBy: context.isSuperAdmin ? 'super_admin' : context.member.userId,
    },
  });
  return { ok: true };
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
    if (event.action === 'updateOrderEntryMode') return updateOrderEntryMode(context, event);
    if (event.action === 'rotateShopCode') return rotateShopCode(context);
    if (event.action === 'listTables') return { ok: true, tables: await listTables(context) };
    if (event.action === 'addTable') return addTable(context, event);
    if (event.action === 'updateTableEnabled') return updateTableEnabled(context, event);
    if (event.action === 'rotateTableCode') return rotateTableCode(context, event);
    if (event.action === 'listShopMembers') return listShopMembers(context);
    if (event.action === 'searchUsers') return searchUsers(context, event);
    if (event.action === 'grantShopMember') return grantShopMember(context, event);
    if (event.action === 'grantSelfOwner') return grantSelfOwner(context);
    if (event.action === 'revokeShopMember') return revokeShopMember(context, event);
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
