const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();

// ==== 配置 ====
// 会话有效期（毫秒）
const SESSION_TTL = 2 * 60 * 60 * 1000;
// 允许跨域访问的来源。正式环境只放行静态托管域名 + 本地开发端口，不再用 '*'。
// 浏览器发来的 Origin 只有「协议+域名」，不带路径和结尾斜杠，这里也照此填写。
const ALLOWED_ORIGINS = [
  'https://cloud1-d2gua37h7753f3812-1454825551.tcloudbaseapp.com', // 线上后台（静态托管）
  'http://localhost:5173', // 本地开发（npm run dev）
];
// 密码哈希参数
const PBKDF2_ITERATIONS = 100000;
const PBKDF2_KEYLEN = 32;
const PBKDF2_DIGEST = 'sha256';

// ==== 通用工具 ====
function corsHeaders(origin) {
  const allowOrigin = ALLOWED_ORIGINS.includes('*')
    ? '*'
    : (ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0] || '');
  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    'Content-Type': 'application/json; charset=utf-8',
  };
}

function httpResponse(statusCode, data, origin) {
  return {
    statusCode,
    headers: corsHeaders(origin),
    body: JSON.stringify(data),
    isBase64Encoded: false,
  };
}

// 解析请求：兼容 HTTP 访问服务（event 带 httpMethod/body）与 wx.cloud.callFunction（event 即 payload）
function parseRequest(event) {
  if (event && typeof event.httpMethod === 'string') {
    const method = event.httpMethod.toUpperCase();
    const origin = (event.headers && (event.headers.origin || event.headers.Origin)) || '';
    let payload = {};
    if (event.body) {
      const raw = event.isBase64Encoded ? Buffer.from(event.body, 'base64').toString('utf8') : event.body;
      try {
        payload = JSON.parse(raw || '{}');
      } catch (error) {
        payload = { __parseError: true };
      }
    }
    return { isHttp: true, method, origin, payload };
  }
  return { isHttp: false, method: 'POST', origin: '', payload: event || {} };
}

function hashPassword(password, salt) {
  return crypto.pbkdf2Sync(password, salt, PBKDF2_ITERATIONS, PBKDF2_KEYLEN, PBKDF2_DIGEST).toString('hex');
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(String(left));
  const rightBuffer = Buffer.from(String(right));
  if (leftBuffer.length !== rightBuffer.length) return false;
  return crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

function hashToken(token) {
  return crypto.createHash('sha256').update(String(token)).digest('hex');
}

// 读一个可能尚未创建的集合：集合不存在时当作空结果，避免首次初始化时抛错
async function safeGet(query) {
  try {
    return await query.get();
  } catch (error) {
    const message = String(error && (error.errMsg || error.message) || '');
    if (error && (error.errCode === -502005 || /not exist|not found/i.test(message))) {
      return { data: [] };
    }
    throw error;
  }
}

// ==== 业务常量与工具（口径与小程序 shop-admin / admin-menu 保持一致）====
const _ = db.command;
const STORE_OWNER = 'store_owner';
const STORE_STAFF = 'store_staff';
const SHOP_MANAGER_ROLES = [STORE_OWNER, STORE_STAFF, 'store_admin'];
const GRANTABLE_ROLES = [STORE_OWNER, STORE_STAFF];

async function bumpShopVersions(shopId, components) {
  const version = Date.now();
  const data = { updatedAt: db.serverDate() };
  components.forEach((component) => {
    data[`${component}Version`] = version;
  });
  await db.collection('shops').doc(shopId).update({ data });
}
const SYSTEM_ID_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const SYSTEM_ID_LENGTH = 8;

function normalizeMemberRole(role) {
  const value = String(role || '');
  if (value === 'store_admin') return STORE_OWNER;
  if (value === STORE_OWNER || value === STORE_STAFF) return value;
  return 'customer';
}

function roleText(role) {
  return normalizeMemberRole(role) === STORE_OWNER ? '一级管理员' : '二级管理员';
}

function normalizeAvatarFileId(value) {
  const fileId = String(value || '').trim();
  return fileId.startsWith('cloud://') ? fileId.slice(0, 512) : '';
}

function createShopCode() {
  return crypto.randomBytes(4).toString('hex').toUpperCase();
}

function hashShopCode(code) {
  return crypto.createHash('sha256').update(String(code)).digest('hex');
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

function createSystemId() {
  const bytes = crypto.randomBytes(SYSTEM_ID_LENGTH);
  let value = '';
  for (let index = 0; index < SYSTEM_ID_LENGTH; index += 1) {
    value += SYSTEM_ID_CHARS[bytes[index] % SYSTEM_ID_CHARS.length];
  }
  return value;
}

async function ensureUserSystemId(user) {
  if (!user || user.systemId) return user;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const systemId = createSystemId();
    const exists = await db.collection('users').where({ systemId }).limit(1).get();
    if (!exists.data.length) {
      await db.collection('users').doc(user._id).update({ data: { systemId, updatedAt: db.serverDate() } });
      return { ...user, systemId };
    }
  }
  return user;
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

async function attachAvatarUrls(items) {
  const fileIds = [...new Set(items.map((item) => normalizeAvatarFileId(item.avatarFileId)).filter(Boolean))];
  if (!fileIds.length) return items.map((item) => ({ ...item, avatarUrl: '' }));
  try {
    const result = await cloud.getTempFileURL({ fileList: fileIds });
    const urls = new Map((result.fileList || [])
      .filter((item) => item.status === 0 && item.tempFileURL)
      .map((item) => [item.fileID, item.tempFileURL]));
    return items.map((item) => ({ ...item, avatarUrl: urls.get(normalizeAvatarFileId(item.avatarFileId)) || '' }));
  } catch (error) {
    return items.map((item) => ({ ...item, avatarUrl: '' }));
  }
}

function escapeRegExp(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// 北京时间「今天」的 UTC 起止（中国无夏令时，固定 UTC+8）
function getChinaDateKeyOf(date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  const values = parts.reduce((result, part) => ({ ...result, [part.type]: part.value }), {});
  return `${values.year}-${values.month}-${values.day}`;
}

function getChinaTodayRange() {
  const [year, month, day] = getChinaDateKeyOf(new Date()).split('-').map(Number);
  const start = new Date(Date.UTC(year, month - 1, day, -8, 0, 0, 0));
  return { start, end: new Date(start.getTime() + 24 * 60 * 60 * 1000) };
}

function parseChinaDate(value) {
  const match = String(value || '').trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (utc.getUTCFullYear() !== year || utc.getUTCMonth() !== month - 1 || utc.getUTCDate() !== day) return null;
  return { key: `${match[1]}-${match[2]}-${match[3]}`, start: new Date(Date.UTC(year, month - 1, day, -8, 0, 0, 0)) };
}

function getChinaDateRange(payload) {
  const today = getChinaDateKeyOf(new Date());
  const endInput = String(payload.dateEnd || today).trim();
  const endDate = parseChinaDate(endInput);
  if (!endDate) return { error: '结束日期格式无效' };

  const startInput = String(payload.dateStart || '').trim();
  const defaultStart = new Date(endDate.start.getTime() - 6 * 24 * 60 * 60 * 1000);
  const startDate = startInput
    ? parseChinaDate(startInput)
    : { key: getChinaDateKeyOf(defaultStart), start: defaultStart };
  if (!startDate) return { error: '开始日期格式无效' };
  if (startDate.start.getTime() > endDate.start.getTime()) return { error: '开始日期不能晚于结束日期' };
  const days = Math.floor((endDate.start.getTime() - startDate.start.getTime()) / (24 * 60 * 60 * 1000)) + 1;
  if (days > 31) return { error: '单次最多查询 31 天订单，请缩小日期范围' };
  return {
    start: startDate.start,
    end: new Date(endDate.start.getTime() + 24 * 60 * 60 * 1000),
    dateStart: startDate.key,
    dateEnd: endDate.key,
  };
}

function formatChinaDateTime(value, fallback = '') {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return String(fallback || '—');
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).format(date);
}

function getOrderTimestamp(order) {
  const createdAt = new Date(order.createdAtServer || order.updatedAt || 0).getTime();
  return Number.isNaN(createdAt) ? 0 : createdAt;
}

async function getShopById(shopId) {
  const id = String(shopId || '').trim();
  if (!id) return null;
  const result = await db.collection('shops').doc(id).get().catch(() => null);
  return result && result.data ? result.data : null;
}

async function getUserById(userId) {
  const id = String(userId || '').trim();
  if (!id) return null;
  const result = await db.collection('users').doc(id).get().catch(() => null);
  return result && result.data ? result.data : null;
}

// ==== 业务：店铺管理（#10）====
async function listShops() {
  const shopResult = await db.collection('shops').orderBy('createdAt', 'desc').limit(200).get();
  const memberResult = await db.collection('shop_members')
    .where({ enabled: true, role: _.in(SHOP_MANAGER_ROLES) }).limit(1000).get();
  const counts = new Map();
  memberResult.data.forEach((member) => {
    const bucket = counts.get(member.shopId) || { owner: 0, staff: 0 };
    if (normalizeMemberRole(member.role) === STORE_OWNER) bucket.owner += 1;
    else bucket.staff += 1;
    counts.set(member.shopId, bucket);
  });
  const shops = shopResult.data.map((shop) => {
    const bucket = counts.get(shop._id) || { owner: 0, staff: 0 };
    return {
      id: shop._id,
      name: shop.name,
      enabled: shop.enabled !== false,
      acceptingOrders: shop.acceptingOrders !== false,
      orderEntryMode: shop.orderEntryMode || 'store_entry',
      displayShopCode: String(shop.displayShopCode || ''),
      ownerCount: bucket.owner,
      staffCount: bucket.staff,
      createdAt: shop.createdAt || null,
    };
  });
  return { ok: true, shops };
}

async function createShop(payload, session) {
  const name = String(payload.name || '').trim().slice(0, 20);
  if (!name) return { ok: false, code: 'INVALID_SHOP', message: '店铺名称无效' };
  const duplicate = await db.collection('shops').where({ name }).limit(1).get();
  if (duplicate.data.length) return { ok: false, code: 'SHOP_NAME_EXISTS', message: '已有同名店铺，请使用不同名称' };
  const shopCode = await createUniqueEntryCode();
  const created = await db.collection('shops').add({
    data: {
      name,
      enabled: true,
      acceptingOrders: true,
      closedDates: [],
      orderEntryMode: 'store_entry',
      shopCodeHash: hashShopCode(shopCode),
      displayShopCode: shopCode,
      shopCodeVersion: 1,
      menuVersion: 0,
      orderVersion: 0,
      memberVersion: 0,
      settingsVersion: 0,
      createdBy: `web-admin:${session.username}`,
      createdAt: db.serverDate(),
      updatedAt: db.serverDate(),
    },
  });
  // 网页超管无微信身份，不自动挂店长；建完店后通过「授权」指定一级管理员
  return {
    ok: true,
    shop: { id: created._id, name, enabled: true, orderEntryMode: 'store_entry', ownerCount: 0, staffCount: 0 },
    initialShopCode: shopCode,
  };
}

async function setShopEnabled(payload) {
  const shop = await getShopById(payload.shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };
  const enabled = payload.enabled === true;
  await db.collection('shops').doc(shop._id).update({ data: { enabled, updatedAt: db.serverDate() } });
  await bumpShopVersions(shop._id, ['settings']);
  return { ok: true, shop: { id: shop._id, enabled } };
}

async function rotateShopCode(payload) {
  const shop = await getShopById(payload.shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };
  const shopCode = await createUniqueEntryCode();
  await db.collection('shops').doc(shop._id).update({
    data: {
      shopCodeHash: hashShopCode(shopCode),
      displayShopCode: shopCode,
      shopCodeVersion: Number(shop.shopCodeVersion || 0) + 1,
      updatedAt: db.serverDate(),
    },
  });
  await bumpShopVersions(shop._id, ['settings']);
  return { ok: true, shopCode };
}

// ==== 业务：成员授权与用户搜索（#11）====
async function searchUsers(payload) {
  const keyword = String(payload.keyword || '').trim();
  if (!keyword) return { ok: true, users: [] };
  const shopId = String(payload.shopId || '').trim();
  const nickResult = await db.collection('users').where({
    nickname: db.RegExp({ regexp: escapeRegExp(keyword), options: 'i' }),
    enabled: true,
  }).limit(20).get();
  const upper = keyword.toUpperCase();
  const systemIdResult = /^[A-Z0-9]{6,8}$/.test(upper)
    ? await db.collection('users').where({
      systemId: db.RegExp({ regexp: `^${escapeRegExp(upper)}$`, options: 'i' }),
      enabled: true,
    }).limit(20).get()
    : { data: [] };
  const docResult = /^[a-zA-Z0-9_-]{8,}$/.test(keyword) ? await getUserById(keyword) : null;
  const merged = [...nickResult.data, ...systemIdResult.data];
  if (docResult && docResult.enabled !== false) merged.unshift(docResult);
  const seen = new Set();
  const deduped = [];
  for (const user of merged) {
    if (seen.has(user._id)) continue;
    seen.add(user._id);
    deduped.push(await ensureUserSystemId(user));
    if (deduped.length >= 20) break;
  }
  let memberByUserId = new Map();
  if (shopId) {
    const memberResult = await db.collection('shop_members').where({ shopId }).limit(200).get();
    memberByUserId = new Map(memberResult.data.map((member) => [member.userId, member]));
  }
  const publicUsers = deduped.map((user) => {
    const member = memberByUserId.get(user._id);
    const active = member && member.enabled !== false && SHOP_MANAGER_ROLES.includes(member.role);
    return {
      ...makePublicUser(user),
      memberRole: active ? normalizeMemberRole(member.role) : '',
      memberRoleText: active ? roleText(member.role) : '未授权',
    };
  });
  return { ok: true, users: await attachAvatarUrls(publicUsers) };
}

async function listShopMembers(payload) {
  const shop = await getShopById(payload.shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };
  const result = await db.collection('shop_members').where({ shopId: shop._id }).limit(200).get();
  const members = result.data.filter((member) => member.enabled !== false && SHOP_MANAGER_ROLES.includes(member.role));
  const userPairs = await Promise.all(members.map(async (member) => {
    const user = await getUserById(member.userId);
    return [member.userId, user ? await ensureUserSystemId(user) : null];
  }));
  const userMap = new Map(userPairs);
  const roleOrder = { store_owner: 0, store_admin: 0, store_staff: 1 };
  const publicMembers = members
    .map((member) => {
      const user = userMap.get(member.userId);
      const role = normalizeMemberRole(member.role);
      return {
        id: member._id,
        userId: member.userId,
        systemId: user ? user.systemId || '' : '',
        nickname: user ? user.nickname || '微信用户' : '（用户已删除）',
        avatarFileId: user ? normalizeAvatarFileId(user.avatarFileId) : '',
        role,
        roleText: roleText(role),
        userEnabled: user ? user.enabled !== false : false,
      };
    })
    .sort((left, right) => (roleOrder[left.role] || 9) - (roleOrder[right.role] || 9)
      || left.nickname.localeCompare(right.nickname, 'zh-CN'));
  return {
    ok: true,
    shop: { id: shop._id, name: shop.name, enabled: shop.enabled !== false },
    members: await attachAvatarUrls(publicMembers),
  };
}

async function grantRole(payload) {
  const shop = await getShopById(payload.shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };
  const role = String(payload.role || '').trim();
  if (!GRANTABLE_ROLES.includes(role)) return { ok: false, code: 'INVALID_ROLE', message: '权限无效' };
  const user = await getUserById(payload.userId);
  if (!user || user.enabled === false) return { ok: false, code: 'INVALID_USER', message: '用户不存在或已停用' };
  const targetUser = await ensureUserSystemId(user);
  const existingResult = await db.collection('shop_members')
    .where({ shopId: shop._id, userId: targetUser._id }).limit(1).get();
  const existing = existingResult.data[0];
  if (existing) {
    await db.collection('shop_members').doc(existing._id).update({
      data: { role, enabled: true, updatedAt: db.serverDate(), updatedBy: 'web-admin' },
    });
  } else {
    await db.collection('shop_members').add({
      data: {
        shopId: shop._id,
        userId: targetUser._id,
        role,
        enabled: true,
        createdAt: db.serverDate(),
        updatedAt: db.serverDate(),
        createdBy: 'web-admin',
      },
    });
  }
  await bumpShopVersions(shop._id, ['member']);
  return {
    ok: true,
    member: {
      userId: targetUser._id,
      systemId: targetUser.systemId || '',
      nickname: targetUser.nickname || '微信用户',
      role: normalizeMemberRole(role),
      roleText: roleText(role),
    },
  };
}

async function revokeRole(payload) {
  const shop = await getShopById(payload.shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };
  const userId = String(payload.userId || '').trim();
  if (!userId) return { ok: false, code: 'INVALID_MEMBER', message: '成员无效' };
  const result = await db.collection('shop_members').where({ shopId: shop._id, userId }).limit(1).get();
  const member = result.data[0];
  if (!member || !SHOP_MANAGER_ROLES.includes(member.role)) {
    return { ok: false, code: 'NOT_FOUND', message: '成员不存在' };
  }
  await db.collection('shop_members').doc(member._id).update({
    data: { enabled: false, updatedAt: db.serverDate(), updatedBy: 'web-admin' },
  });
  await bumpShopVersions(shop._id, ['member']);
  return { ok: true };
}

// ==== 业务：平台用户管理 ====
async function getUserMemberSummary(userIds) {
  if (!userIds.length) return new Map();
  const result = await db.collection('shop_members')
    .where({ userId: _.in(userIds), enabled: true, role: _.in(SHOP_MANAGER_ROLES) })
    .limit(1000)
    .get();
  const summary = new Map();
  result.data.forEach((member) => {
    const bucket = summary.get(member.userId) || { ownerCount: 0, staffCount: 0, shopCount: 0, shopIds: new Set() };
    if (normalizeMemberRole(member.role) === STORE_OWNER) bucket.ownerCount += 1;
    else bucket.staffCount += 1;
    if (member.shopId && !bucket.shopIds.has(member.shopId)) {
      bucket.shopIds.add(member.shopId);
      bucket.shopCount += 1;
    }
    summary.set(member.userId, bucket);
  });
  return summary;
}

async function listUsers(payload) {
  const keyword = String(payload.keyword || '').trim();
  const pageSize = Math.min(Math.max(Number(payload.pageSize) || 30, 10), 50);
  const page = Math.max(Number(payload.page) || 1, 1);
  let users = [];

  if (keyword) {
    const nickResult = await db.collection('users').where({
      nickname: db.RegExp({ regexp: escapeRegExp(keyword), options: 'i' }),
    }).limit(pageSize).get();
    const upper = keyword.toUpperCase();
    const systemIdResult = /^[A-Z0-9]{6,8}$/.test(upper)
      ? await db.collection('users').where({
        systemId: db.RegExp({ regexp: `^${escapeRegExp(upper)}$`, options: 'i' }),
      }).limit(pageSize).get()
      : { data: [] };
    const docResult = /^[a-zA-Z0-9_-]{8,}$/.test(keyword) ? await getUserById(keyword) : null;
    const merged = [...nickResult.data, ...systemIdResult.data];
    if (docResult) merged.unshift(docResult);
    const seen = new Set();
    for (const user of merged) {
      if (!user || seen.has(user._id)) continue;
      seen.add(user._id);
      users.push(await ensureUserSystemId(user));
      if (users.length >= pageSize) break;
    }
  } else {
    const result = await db.collection('users')
      .orderBy('createdAt', 'desc')
      .skip((page - 1) * pageSize)
      .limit(pageSize)
      .get();
    users = await Promise.all(result.data.map((user) => ensureUserSystemId(user)));
  }

  const summary = await getUserMemberSummary(users.map((user) => user._id));
  const publicUsers = users.map((user) => {
    const member = summary.get(user._id) || { ownerCount: 0, staffCount: 0, shopCount: 0 };
    return {
      ...makePublicUser(user),
      profileCompleted: user.profileCompleted === true,
      phoneNumber: user.phoneNumber ? String(user.phoneNumber).replace(/^(\d{3})\d{4}(\d+)/, '$1****$2') : '',
      shopCount: member.shopCount || 0,
      ownerCount: member.ownerCount || 0,
      staffCount: member.staffCount || 0,
      createdAt: user.createdAt || null,
    };
  });
  return {
    ok: true,
    users: await attachAvatarUrls(publicUsers),
    page,
    pageSize,
    hasMore: !keyword && users.length === pageSize,
  };
}

async function setUserEnabled(payload) {
  const user = await getUserById(payload.userId);
  if (!user) return { ok: false, code: 'USER_NOT_FOUND', message: '用户不存在' };
  if (user.role === 'super_admin') {
    return { ok: false, code: 'CANNOT_DISABLE_SUPER_ADMIN', message: '不能在这里停用小程序超级管理员' };
  }
  const enabled = payload.enabled === true;
  await db.collection('users').doc(user._id).update({ data: { enabled, updatedAt: db.serverDate() } });
  return { ok: true, user: { id: user._id, enabled } };
}

// ==== 业务：跨店订单只读监管 ====
const PLATFORM_ORDER_STATUSES = ['制作中', '已完成', '已取消'];
const PLATFORM_ORDER_FETCH_LIMIT = 5000;
const SHOP_BACKUP_ORDER_LIMIT = 5000;

function makePlatformOrderSummary(order, shopNames) {
  return {
    recordId: order._id,
    orderId: order.id || order._id,
    shopId: order.shopId || '',
    shopName: shopNames.get(order.shopId) || '（未知店铺）',
    tableName: order.tableName || '未扫码桌位',
    orderChannel: order.orderChannel || 'store_entry',
    status: order.status || '制作中',
    total: Number(order.total || 0).toFixed(2),
    createdAt: formatChinaDateTime(order.createdAtServer, order.createdAt),
  };
}

function makePlatformOrderDetail(order, shopNames) {
  return {
    ...makePlatformOrderSummary(order, shopNames),
    statusNote: order.statusNote || '',
    remark: order.remark || '',
    items: (Array.isArray(order.items) ? order.items : []).map((item) => ({
      id: item.id || '',
      name: item.name || '菜品',
      price: Number(item.price || 0).toFixed(2),
      quantity: Number(item.quantity || 0),
      options: Array.isArray(item.options) ? item.options : [],
      optionsText: item.optionsText || '',
    })),
  };
}

async function getShopNameMap() {
  const result = await db.collection('shops').field({ name: true }).limit(200).get();
  return new Map(result.data.map((shop) => [shop._id, shop.name]));
}

async function fetchPlatformOrders(range, fields) {
  const orders = [];
  for (let skip = 0; skip < PLATFORM_ORDER_FETCH_LIMIT; skip += 100) {
    const result = await db.collection('orders').where({
      createdAtServer: _.gte(range.start).and(_.lt(range.end)),
    }).field(fields).skip(skip).limit(100).get();
    orders.push(...result.data);
    if (result.data.length < 100) break;
  }
  return { orders, truncated: orders.length >= PLATFORM_ORDER_FETCH_LIMIT };
}

async function listPlatformOrders(payload) {
  const range = getChinaDateRange(payload);
  if (range.error) return { ok: false, code: 'INVALID_DATE_RANGE', message: range.error };
  const shopId = String(payload.shopId || '').trim();
  const status = String(payload.status || '').trim();
  if (status && !PLATFORM_ORDER_STATUSES.includes(status)) {
    return { ok: false, code: 'INVALID_ORDER_STATUS', message: '订单状态无效' };
  }
  const pageSize = Math.min(Math.max(Number(payload.pageSize) || 20, 10), 50);
  const page = Math.max(Number(payload.page) || 1, 1);
  // 先按日期读取并在云函数内筛选，避免组合筛选依赖额外的数据库复合索引。
  const source = await fetchPlatformOrders(range, {
    id: true, shopId: true, tableName: true, orderChannel: true, status: true,
    total: true, createdAt: true, createdAtServer: true, updatedAt: true,
  });
  const filtered = source.orders
    .filter((order) => (!shopId || order.shopId === shopId) && (!status || order.status === status))
    .sort((left, right) => getOrderTimestamp(right) - getOrderTimestamp(left));
  const shopNames = await getShopNameMap();
  const startIndex = (page - 1) * pageSize;
  const orders = filtered.slice(startIndex, startIndex + pageSize).map((order) => makePlatformOrderSummary(order, shopNames));
  return {
    ok: true,
    orders,
    page,
    pageSize,
    total: filtered.length,
    hasMore: startIndex + orders.length < filtered.length,
    truncated: source.truncated,
    dateStart: range.dateStart,
    dateEnd: range.dateEnd,
  };
}

async function getPlatformOrderDetail(payload) {
  const recordId = String(payload.recordId || '').trim();
  if (!recordId) return { ok: false, code: 'INVALID_ORDER', message: '订单参数无效' };
  const result = await db.collection('orders').doc(recordId).get().catch(() => null);
  if (!result || !result.data) return { ok: false, code: 'ORDER_NOT_FOUND', message: '订单不存在或已删除' };
  const shopNames = await getShopNameMap();
  return { ok: true, order: makePlatformOrderDetail(result.data, shopNames) };
}

function createDateBuckets(range) {
  const buckets = new Map();
  for (let time = range.start.getTime(); time < range.end.getTime(); time += 24 * 60 * 60 * 1000) {
    const dateKey = getChinaDateKeyOf(new Date(time));
    buckets.set(dateKey, { dateKey, revenue: 0, orderCount: 0 });
  }
  return buckets;
}

async function getPlatformReport(payload) {
  const range = getChinaDateRange(payload);
  if (range.error) return { ok: false, code: 'INVALID_DATE_RANGE', message: range.error };
  const shopId = String(payload.shopId || '').trim();
  const source = await fetchPlatformOrders(range, {
    shopId: true, status: true, total: true, items: true, createdAtServer: true,
  });
  const orders = source.orders.filter((order) => !shopId || order.shopId === shopId);
  const shopNames = await getShopNameMap();
  const daily = createDateBuckets(range);
  const shops = new Map();
  const dishes = new Map();
  let revenue = 0;
  let completedCount = 0;
  let makingCount = 0;

  let cancelledCount = 0;
  orders.forEach((order) => {
    if (order.status === '制作中') makingCount += 1;
    if (order.status === '已取消') {
      cancelledCount += 1;
      return;
    }
    if (order.status !== '已完成') return;
    const total = Number(order.total) || 0;
    revenue += total;
    completedCount += 1;
    const dateKey = getChinaDateKeyOf(new Date(order.createdAtServer));
    const day = daily.get(dateKey);
    if (day) { day.revenue += total; day.orderCount += 1; }
    const shop = shops.get(order.shopId) || { shopId: order.shopId, orderCount: 0, revenue: 0 };
    shop.orderCount += 1;
    shop.revenue += total;
    shops.set(order.shopId, shop);
    (Array.isArray(order.items) ? order.items : []).forEach((item) => {
      const name = String(item.name || '菜品');
      const dish = dishes.get(name) || { name, quantity: 0, revenue: 0 };
      const quantity = Number(item.quantity) || 0;
      dish.quantity += quantity;
      dish.revenue += (Number(item.price) || 0) * quantity;
      dishes.set(name, dish);
    });
  });
  return {
    ok: true,
    report: {
      dateStart: range.dateStart,
      dateEnd: range.dateEnd,
      orderCount: orders.length,
      revenue: Number(revenue.toFixed(2)),
      completedCount,
      makingCount,
      cancelledCount,
      averageOrderValue: completedCount ? Number((revenue / completedCount).toFixed(2)) : 0,
      daily: [...daily.values()].map((item) => ({ ...item, revenue: Number(item.revenue.toFixed(2)) })),
      topShops: [...shops.values()]
        .map((item) => ({ ...item, name: shopNames.get(item.shopId) || '（未知店铺）', revenue: Number(item.revenue.toFixed(2)) }))
        .sort((left, right) => right.revenue - left.revenue || right.orderCount - left.orderCount).slice(0, 10),
      topDishes: [...dishes.values()]
        .map((item) => ({ ...item, revenue: Number(item.revenue.toFixed(2)) }))
        .sort((left, right) => right.quantity - left.quantity || right.revenue - left.revenue).slice(0, 10),
      truncated: source.truncated,
    },
  };
}

async function exportPlatformOrders(payload) {
  const range = getChinaDateRange(payload);
  if (range.error) return { ok: false, code: 'INVALID_DATE_RANGE', message: range.error };
  const shopId = String(payload.shopId || '').trim();
  const status = String(payload.status || '').trim();
  if (status && !PLATFORM_ORDER_STATUSES.includes(status)) return { ok: false, code: 'INVALID_ORDER_STATUS', message: '订单状态无效' };
  const source = await fetchPlatformOrders(range, {
    id: true, shopId: true, tableName: true, orderChannel: true, status: true, total: true,
    createdAt: true, createdAtServer: true, remark: true, items: true,
  });
  const shopNames = await getShopNameMap();
  const rows = [];
  source.orders
    .filter((order) => (!shopId || order.shopId === shopId) && (!status || order.status === status))
    .sort((left, right) => getOrderTimestamp(right) - getOrderTimestamp(left))
    .forEach((order) => {
      const items = Array.isArray(order.items) && order.items.length ? order.items : [{}];
      items.forEach((item) => rows.push({
        orderId: order.id || order._id,
        createdAt: formatChinaDateTime(order.createdAtServer, order.createdAt),
        shopName: shopNames.get(order.shopId) || '（未知店铺）',
        tableName: order.tableName || '未扫码桌位',
        channel: order.orderChannel === 'table' ? '桌码下单' : '店铺入口下单',
        status: order.status || '',
        dishName: item.name || '',
        options: item.optionsText || (Array.isArray(item.options) ? item.options.join('、') : ''),
        price: Number(item.price || 0).toFixed(2),
        quantity: Number(item.quantity || 0),
        total: Number(order.total || 0).toFixed(2),
        remark: order.remark || '',
      }));
    });
  return { ok: true, rows, truncated: source.truncated, dateStart: range.dateStart, dateEnd: range.dateEnd };
}

function makeBackupFileName(shopId, dateStart, dateEnd) {
  return `shop-backups/${shopId}/backup_${dateStart}_${dateEnd}_${Date.now()}.json`;
}

function makeBackupShop(shop) {
  const { _id, ...settings } = shop || {};
  return { recordId: _id || '', ...settings };
}

function makeBackupOrder(order) {
  const { _id, ...snapshot } = order || {};
  return { recordId: _id || '', ...snapshot };
}

async function getAllShopDocuments(collectionName, shopId) {
  const documents = [];
  for (let skip = 0; skip < 1000; skip += 100) {
    const result = await db.collection(collectionName).where({ shopId }).skip(skip).limit(100).get();
    documents.push(...result.data);
    if (result.data.length < 100) break;
  }
  return documents;
}

async function getBackupOrders(shopId, range) {
  const orders = [];
  for (let skip = 0; skip <= SHOP_BACKUP_ORDER_LIMIT; skip += 100) {
    const result = await db.collection('orders').where({
      shopId,
      createdAtServer: _.gte(range.start).and(_.lt(range.end)),
    }).skip(skip).limit(100).get();
    orders.push(...result.data);
    if (orders.length > SHOP_BACKUP_ORDER_LIMIT) {
      const error = new Error(`订单数量超过 ${SHOP_BACKUP_ORDER_LIMIT} 笔，请缩小日期范围后再备份`);
      error.code = 'BACKUP_ORDER_LIMIT';
      throw error;
    }
    if (result.data.length < 100) break;
  }
  return orders;
}

async function createShopBackup(payload, session) {
  const shopId = String(payload.shopId || '').trim();
  const range = getChinaDateRange(payload);
  if (!shopId) return { ok: false, code: 'INVALID_SHOP', message: '请选择需要备份的店铺' };
  if (range.error) return { ok: false, code: 'INVALID_DATE_RANGE', message: range.error };
  const shop = await getShopById(shopId);
  if (!shop) return { ok: false, code: 'SHOP_NOT_FOUND', message: '店铺不存在' };

  let uploadedFileId = '';
  try {
    const [categories, dishes, tables, orders] = await Promise.all([
      getAllShopDocuments('categories', shopId),
      getAllShopDocuments('dishes', shopId),
      getAllShopDocuments('shop_tables', shopId),
      getBackupOrders(shopId, range),
    ]);
    const createdAt = new Date().toISOString();
    const backup = {
      schemaVersion: 1,
      generatedAt: createdAt,
      timezone: 'Asia/Shanghai',
      orderDateRange: { start: range.dateStart, end: range.dateEnd },
      shop: makeBackupShop(shop),
      categories,
      dishes,
      tables,
      orders: orders.map(makeBackupOrder),
    };
    const content = Buffer.from(JSON.stringify(backup, null, 2), 'utf8');
    const fileName = makeBackupFileName(shopId, range.dateStart, range.dateEnd);
    const uploadResult = await cloud.uploadFile({ cloudPath: fileName, fileContent: content });
    uploadedFileId = uploadResult.fileID;
    const metadata = {
      shopId,
      shopName: shop.name || '未命名店铺',
      fileId: uploadedFileId,
      fileName: fileName.split('/').pop(),
      schemaVersion: 1,
      dateStart: range.dateStart,
      dateEnd: range.dateEnd,
      orderCount: orders.length,
      byteSize: content.length,
      createdBy: session.username || '',
      createdAt: db.serverDate(),
    };
    const result = await db.collection('shop_backups').add({ data: metadata });
    return { ok: true, backup: { id: result._id, ...metadata } };
  } catch (error) {
    if (uploadedFileId) await cloud.deleteFile({ fileList: [uploadedFileId] }).catch(() => {});
    return { ok: false, code: error.code || 'CREATE_BACKUP_FAILED', message: error.message || '生成备份失败' };
  }
}

async function attachBackupUrls(backups) {
  const fileIds = backups.map((item) => item.fileId).filter(Boolean);
  if (!fileIds.length) return backups.map((item) => ({ ...item, downloadUrl: '' }));
  const urlMap = new Map();
  for (let index = 0; index < fileIds.length; index += 50) {
    const result = await cloud.getTempFileURL({ fileList: fileIds.slice(index, index + 50) }).catch(() => ({ fileList: [] }));
    (result.fileList || []).filter((item) => item.status === 0 && item.tempFileURL)
      .forEach((item) => urlMap.set(item.fileID, item.tempFileURL));
  }
  return backups.map((item) => ({ ...item, downloadUrl: urlMap.get(item.fileId) || '' }));
}

async function listShopBackups(payload) {
  const shopId = String(payload.shopId || '').trim();
  const query = shopId ? db.collection('shop_backups').where({ shopId }) : db.collection('shop_backups');
  const result = await safeGet(query.orderBy('createdAt', 'desc').limit(100));
  const backups = await attachBackupUrls(result.data || []);
  return {
    ok: true,
    backups: backups.map((item) => ({
      id: item._id,
      shopId: item.shopId,
      shopName: item.shopName,
      fileName: item.fileName,
      dateStart: item.dateStart,
      dateEnd: item.dateEnd,
      orderCount: Number(item.orderCount || 0),
      byteSize: Number(item.byteSize || 0),
      createdBy: item.createdBy || '',
      createdAt: formatChinaDateTime(item.createdAt),
      downloadUrl: item.downloadUrl,
    })),
  };
}

// ==== 业务：跨店数据总览（#12）====
async function getPlatformOverview() {
  const { start, end } = getChinaTodayRange();
  const [shopsTotal, shopsEnabled, usersTotal] = await Promise.all([
    db.collection('shops').count(),
    db.collection('shops').where({ enabled: _.neq(false) }).count(),
    db.collection('users').where({ enabled: _.neq(false) }).count(),
  ]);
  const memberResult = await db.collection('shop_members')
    .where({ enabled: true, role: _.in(SHOP_MANAGER_ROLES) }).limit(1000).get();
  let ownerCount = 0;
  let staffCount = 0;
  memberResult.data.forEach((member) => {
    if (normalizeMemberRole(member.role) === STORE_OWNER) ownerCount += 1;
    else staffCount += 1;
  });

  // 今日订单（跨店，不加 shopId 过滤）
  const orders = [];
  const pageSize = 100;
  for (let skip = 0; skip < 20000; skip += pageSize) {
    const page = await db.collection('orders')
      .where({ createdAtServer: _.gte(start).and(_.lt(end)) })
      .field({ shopId: true, total: true, status: true })
      .skip(skip).limit(pageSize).get();
    orders.push(...page.data);
    if (page.data.length < pageSize) break;
  }
  let todayRevenue = 0;
  let completedCount = 0;
  const perShop = new Map();
  let cancelledCount = 0;
  orders.forEach((order) => {
    if (order.status === '已取消') {
      cancelledCount += 1;
      return;
    }
    if (order.status !== '已完成') return;
    const total = Number(order.total) || 0;
    todayRevenue += total;
    completedCount += 1;
    const bucket = perShop.get(order.shopId) || { shopId: order.shopId, orderCount: 0, revenue: 0 };
    bucket.orderCount += 1;
    bucket.revenue += total;
    perShop.set(order.shopId, bucket);
  });

  const shopNameResult = await db.collection('shops').field({ name: true }).limit(200).get();
  const shopNames = new Map(shopNameResult.data.map((shop) => [shop._id, shop.name]));
  const topShops = [...perShop.values()]
    .map((item) => ({ ...item, name: shopNames.get(item.shopId) || '（未知店铺）', revenue: Number(item.revenue.toFixed(2)) }))
    .sort((left, right) => right.revenue - left.revenue || right.orderCount - left.orderCount)
    .slice(0, 10);

  return {
    ok: true,
    overview: {
      dateKey: getChinaDateKeyOf(new Date()),
      shopsTotal: shopsTotal.total,
      shopsEnabled: shopsEnabled.total,
      usersTotal: usersTotal.total,
      ownerCount,
      staffCount,
      todayOrderCount: orders.length,
      todayRevenue: Number(todayRevenue.toFixed(2)),
      todayCompletedCount: completedCount,
      todayCancelledCount: cancelledCount,
      topShops,
    },
  };
}

// ==== 鉴权 ====
async function requireSuperAdmin(token) {
  const cleanToken = String(token || '').trim();
  if (!cleanToken) {
    const error = new Error('请先登录');
    error.code = 'UNAUTHORIZED';
    throw error;
  }
  const result = await safeGet(db.collection('web_sessions').where({ tokenHash: hashToken(cleanToken) }).limit(1));
  const session = result.data[0];
  if (!session || new Date(session.expiresAt || 0).getTime() <= Date.now()) {
    const error = new Error('登录已过期，请重新登录');
    error.code = 'SESSION_EXPIRED';
    throw error;
  }
  return session;
}

// ==== 账号引导与登录 ====
// 首次初始化：仅当 web_admins 集合为空时可用，用于设定第一个超管账号
async function setupAdmin(payload) {
  const existing = await safeGet(db.collection('web_admins').limit(1));
  if (existing.data.length) {
    return { ok: false, code: 'ALREADY_INITIALIZED', message: '超管账号已存在，初始化入口已关闭' };
  }
  const username = String(payload.username || '').trim();
  const password = String(payload.password || '');
  if (username.length < 3 || username.length > 32) {
    return { ok: false, code: 'INVALID_USERNAME', message: '账号需为 3~32 位' };
  }
  if (password.length < 8) {
    return { ok: false, code: 'WEAK_PASSWORD', message: '密码至少 8 位' };
  }
  const salt = crypto.randomBytes(16).toString('hex');
  await db.collection('web_admins').add({
    data: {
      username,
      salt,
      passwordHash: hashPassword(password, salt),
      enabled: true,
      createdAt: db.serverDate(),
      lastLoginAt: null,
    },
  });
  return { ok: true, username };
}

async function login(payload) {
  const username = String(payload.username || '').trim();
  const password = String(payload.password || '');
  if (!username || !password) {
    return { ok: false, code: 'INVALID_CREDENTIALS', message: '请输入账号和密码' };
  }
  const result = await safeGet(db.collection('web_admins').where({ username, enabled: true }).limit(1));
  const admin = result.data[0];
  // 无论账号是否存在都执行一次哈希，降低时序区分；统一返回同一提示避免暴露账号存在性
  const salt = admin ? admin.salt : 'placeholder-salt';
  const computed = hashPassword(password, salt);
  const passwordOk = admin && safeEqual(computed, admin.passwordHash);
  if (!admin || !passwordOk) {
    return { ok: false, code: 'INVALID_CREDENTIALS', message: '账号或密码错误' };
  }
  const token = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + SESSION_TTL);
  await db.collection('web_sessions').add({
    data: { tokenHash: hashToken(token), username, expiresAt, createdAt: db.serverDate() },
  });
  await db.collection('web_admins').doc(admin._id).update({ data: { lastLoginAt: db.serverDate() } });
  return { ok: true, token, expiresAt: expiresAt.toISOString(), username };
}

async function logout(payload) {
  const token = String(payload.token || '').trim();
  if (token) {
    await db.collection('web_sessions').where({ tokenHash: hashToken(token) }).remove().catch(() => {});
  }
  return { ok: true };
}

// ==== 需要登录后才能访问的操作 ====
// 具体业务在后续任务中补充（店铺管理 / 授权 / 跨店总览）
async function handleAuthedAction(action, payload, session) {
  switch (action) {
    case 'me':
      return { ok: true, username: session.username };
    // #10 店铺管理
    case 'listShops':
      return listShops();
    case 'createShop':
      return createShop(payload, session);
    case 'setShopEnabled':
      return setShopEnabled(payload);
    case 'rotateShopCode':
      return rotateShopCode(payload);
    // #11 成员授权与用户搜索
    case 'searchUsers':
      return searchUsers(payload);
    case 'listShopMembers':
      return listShopMembers(payload);
    case 'grantRole':
      return grantRole(payload);
    case 'revokeRole':
      return revokeRole(payload);
    // 平台用户管理
    case 'listUsers':
      return listUsers(payload);
    case 'setUserEnabled':
      return setUserEnabled(payload);
    // 跨店订单只读监管
    case 'listPlatformOrders':
      return listPlatformOrders(payload);
    case 'getPlatformOrderDetail':
      return getPlatformOrderDetail(payload);
    case 'getPlatformReport':
      return getPlatformReport(payload);
    case 'exportPlatformOrders':
      return exportPlatformOrders(payload);
    case 'createShopBackup':
      return createShopBackup(payload, session);
    case 'listShopBackups':
      return listShopBackups(payload);
    // #12 跨店总览
    case 'getPlatformOverview':
      return getPlatformOverview();
    default:
      return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
  }
}

exports.main = async (event) => {
  const { isHttp, method, origin, payload } = parseRequest(event);
  const wrap = (data, statusCode = 200) => (isHttp ? httpResponse(statusCode, data, origin) : data);

  // CORS 预检
  if (isHttp && method === 'OPTIONS') return wrap({ ok: true });
  if (payload && payload.__parseError) return wrap({ ok: false, code: 'BAD_REQUEST', message: '请求格式错误' }, 400);

  const action = String(payload.action || '').trim();
  try {
    // 免登录入口：仅 setup 与 login
    if (action === 'setup') return wrap(await setupAdmin(payload));
    if (action === 'login') return wrap(await login(payload));
    if (action === 'logout') return wrap(await logout(payload));

    // 其余一律需要有效的超管会话
    const session = await requireSuperAdmin(payload.token);
    return wrap(await handleAuthedAction(action, payload, session));
  } catch (error) {
    const code = error.code || 'WEB_ADMIN_ERROR';
    const message = error.code ? error.message : '服务暂时不可用，请稍后重试';
    const statusCode = ['UNAUTHORIZED', 'SESSION_EXPIRED'].includes(code) ? 401 : 200;
    console.error('web-admin 执行失败', { action, code, message });
    return wrap({ ok: false, code, message }, statusCode);
  }
};
