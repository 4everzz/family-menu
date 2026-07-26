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
      shopCodeVersion: 1,
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
  return { ok: true, shop: { id: shop._id, enabled } };
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
  return { ok: true };
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
  orders.forEach((order) => {
    const total = Number(order.total) || 0;
    todayRevenue += total;
    if (order.status === '已完成') completedCount += 1;
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
    // #11 成员授权与用户搜索
    case 'searchUsers':
      return searchUsers(payload);
    case 'listShopMembers':
      return listShopMembers(payload);
    case 'grantRole':
      return grantRole(payload);
    case 'revokeRole':
      return revokeRole(payload);
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
