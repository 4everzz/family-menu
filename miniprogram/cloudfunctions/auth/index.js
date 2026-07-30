const cloud = require('wx-server-sdk');
const crypto = require('crypto');

cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV });

const db = cloud.database();
const ROLES = {
  USER: 'user',
  MANAGER: 'manager',
  SUPER_ADMIN: 'super_admin',
};
const SYSTEM_ID_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const SYSTEM_ID_LENGTH = 8;
const RESET_NICKNAME_MAX_LENGTH = 12;

function normalizeAvatarFileId(value) {
  const avatarFileId = String(value || '').trim();
  return avatarFileId.startsWith('cloud://') ? avatarFileId.slice(0, 512) : '';
}

function isProfileCompleted(user) {
  const nickname = String(user && user.nickname || '').trim();
  return !!nickname && nickname !== '微信用户';
}

function normalizeNicknameForComparison(value) {
  return String(value || '').trim().replace(/\s+/g, '').toUpperCase();
}

async function findNicknameRestriction(nickname) {
  const normalizedNickname = normalizeNicknameForComparison(nickname);
  if (!normalizedNickname) return '';
  const result = await db.collection('nickname_restrictions').limit(100).get().catch(() => ({ data: [] }));
  const matched = (result.data || []).find((item) => {
    const word = normalizeNicknameForComparison(item.normalizedWord || item.word);
    return word && normalizedNickname.includes(word);
  });
  return matched ? String(matched.word || '').trim() : '';
}

function makePublicUser(user) {
  return {
    id: user._id,
    systemId: user.systemId || '',
    nickname: user.nickname || '微信用户',
    avatarFileId: normalizeAvatarFileId(user.avatarFileId),
    profileCompleted: isProfileCompleted(user),
    profileReset: !!user.profileResetAt,
    role: user.role,
    enabled: user.enabled !== false,
  };
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

async function ensureSystemId(user) {
  if (user && user.systemId) return user;
  const systemId = await createUniqueSystemId();
  await db.collection('users').doc(user._id).update({
    data: { systemId, updatedAt: db.serverDate() },
  });
  return { ...user, systemId };
}

async function attachAvatarUrls(users) {
  const fileIds = [...new Set(users.map((user) => normalizeAvatarFileId(user.avatarFileId)).filter(Boolean))];
  if (!fileIds.length) return users.map((user) => ({ ...user, avatarUrl: '' }));
  try {
    const result = await cloud.getTempFileURL({ fileList: fileIds });
    const avatarUrls = new Map((result.fileList || [])
      .filter((item) => item.status === 0 && item.tempFileURL)
      .map((item) => [item.fileID, item.tempFileURL]));
    return users.map((user) => ({
      ...user,
      avatarUrl: avatarUrls.get(normalizeAvatarFileId(user.avatarFileId)) || '',
    }));
  } catch (error) {
    return users.map((user) => ({ ...user, avatarUrl: '' }));
  }
}

async function makePublicUserWithAvatar(user) {
  const [publicUser] = await attachAvatarUrls([makePublicUser(user)]);
  return publicUser;
}

async function findUserByOpenId(openId) {
  const result = await db.collection('users').where({ openId }).limit(1).get();
  return result.data[0] || null;
}

async function isLegacyManager(openId) {
  const result = await db.collection('admins').where({ openId, enabled: true }).limit(1).get();
  return result.data.length > 0;
}

async function hasSuperAdmin() {
  const result = await db.collection('users').where({ role: ROLES.SUPER_ADMIN }).limit(1).get();
  return result.data.length > 0;
}

async function migrateLegacySuperAdmin(openId) {
  if (!(await isLegacyManager(openId))) return null;
  const result = await db.collection('users').where({ role: ROLES.SUPER_ADMIN }).limit(10).get();
  const legacyUser = result.data.find((item) => !item.openId);
  if (!legacyUser) return null;
  const systemId = legacyUser.systemId || await createUniqueSystemId();
  await db.collection('users').doc(legacyUser._id).update({
    data: {
      openId,
      systemId,
      nickname: legacyUser.nickname || '微信用户',
      updatedAt: db.serverDate(),
    },
  });
  return { ...legacyUser, openId, systemId, nickname: legacyUser.nickname || '微信用户' };
}

async function createUser(openId) {
  const canBootstrap = await isLegacyManager(openId) && !(await hasSuperAdmin());
  const user = {
    openId,
    systemId: await createUniqueSystemId(),
    nickname: '',
    avatarFileId: '',
    role: canBootstrap ? ROLES.SUPER_ADMIN : ROLES.USER,
    enabled: true,
    createdAt: db.serverDate(),
    updatedAt: db.serverDate(),
  };
  const addResult = await db.collection('users').add({ data: user });
  return { ...user, _id: addResult._id };
}

async function loginWithWechat(openId) {
  const existing = await findUserByOpenId(openId);
  if (existing) {
    if (existing.enabled === false) return { ok: false, code: 'ACCOUNT_DISABLED', message: '该账号已被停用' };
    return { ok: true, user: await makePublicUserWithAvatar(await ensureSystemId(existing)) };
  }
  const migratedUser = await migrateLegacySuperAdmin(openId);
  if (migratedUser) return { ok: true, user: await makePublicUserWithAvatar(await ensureSystemId(migratedUser)) };
  const user = await createUser(openId);
  return { ok: true, user: await makePublicUserWithAvatar(user) };
}

async function getCurrentUser(openId) {
  const user = await findUserByOpenId(openId);
  if (!user || user.enabled === false) return { ok: false, code: 'NOT_LOGGED_IN', message: '请先登录' };
  return { ok: true, user: await makePublicUserWithAvatar(await ensureSystemId(user)) };
}

async function updateProfile(openId, event) {
  const user = await findUserByOpenId(openId);
  if (!user || user.enabled === false) return { ok: false, code: 'NOT_LOGGED_IN', message: '请先登录' };
  const nickname = String(event.nickname || '').trim().slice(0, RESET_NICKNAME_MAX_LENGTH);
  const avatarFileId = normalizeAvatarFileId(event.avatarFileId);
  if (!nickname || nickname === '微信用户') {
    return { ok: false, code: 'INVALID_NICKNAME', message: '请填写 1 至 12 个字的昵称' };
  }
  const restrictedWord = await findNicknameRestriction(nickname);
  if (restrictedWord) {
    return { ok: false, code: 'NICKNAME_RESTRICTED', message: '昵称包含限制词，请合理修改后再保存' };
  }
  const userWithSystemId = await ensureSystemId(user);
  const updatedUser = { ...userWithSystemId, nickname, avatarFileId };
  await db.collection('users').doc(user._id).update({
    data: { nickname, avatarFileId, profileResetAt: null, updatedAt: db.serverDate() },
  });
  return { ok: true, user: await makePublicUserWithAvatar(updatedUser) };
}

function makeManagedUser(user) {
  return {
    id: user._id,
    systemId: user.systemId || '',
    nickname: user.nickname || '微信用户',
    avatarFileId: normalizeAvatarFileId(user.avatarFileId),
    profileCompleted: isProfileCompleted(user),
    role: user.role || ROLES.USER,
    enabled: user.enabled !== false,
  };
}

async function requireSuperAdmin(openId) {
  const user = await findUserByOpenId(openId);
  return user && user.enabled !== false && user.role === ROLES.SUPER_ADMIN ? user : null;
}

async function listManagedUsers() {
  const result = await db.collection('users').limit(100).get();
  const roleOrder = { super_admin: 0, manager: 1, user: 2 };
  const usersWithSystemIds = await Promise.all(result.data.map((user) => ensureSystemId(user)));
  const users = usersWithSystemIds
    .sort((left, right) => (roleOrder[left.role] || 9) - (roleOrder[right.role] || 9))
    .map(makeManagedUser);
  return attachAvatarUrls(users);
}

async function updateManagedUserRole(openId, event) {
  const id = String(event.id || '');
  const role = String(event.role || '');
  if (!id || ![ROLES.USER, ROLES.MANAGER].includes(role)) {
    return { ok: false, code: 'INVALID_ROLE', message: '角色信息无效' };
  }
  const result = await db.collection('users').doc(id).get();
  const target = result.data;
  if (!target) return { ok: false, code: 'NOT_FOUND', message: '用户不存在' };
  if (target.openId === openId || target.role === ROLES.SUPER_ADMIN) {
    return { ok: false, code: 'PROTECTED_USER', message: '不能修改超级管理员权限' };
  }
  await db.collection('users').doc(id).update({ data: { role, updatedAt: db.serverDate() } });
  return { ok: true, user: makeManagedUser({ ...target, role }) };
}

async function updateManagedUserEnabled(openId, event) {
  const id = String(event.id || '');
  const enabled = event.enabled === true;
  if (!id) return { ok: false, code: 'INVALID_USER', message: '用户信息无效' };
  const result = await db.collection('users').doc(id).get();
  const target = result.data;
  if (!target) return { ok: false, code: 'NOT_FOUND', message: '用户不存在' };
  if (target.openId === openId || target.role === ROLES.SUPER_ADMIN) {
    return { ok: false, code: 'PROTECTED_USER', message: '不能停用超级管理员' };
  }
  await db.collection('users').doc(id).update({ data: { enabled, updatedAt: db.serverDate() } });
  return { ok: true, user: makeManagedUser({ ...target, enabled }) };
}

exports.main = async (event) => {
  const { OPENID: openId } = cloud.getWXContext();
  try {
    if (event.action === 'loginWithWechat') return await loginWithWechat(openId);
    if (event.action === 'getCurrentUser') return await getCurrentUser(openId);
    if (event.action === 'updateProfile') return await updateProfile(openId, event);
    if (['listUsers', 'updateUserRole', 'updateUserEnabled'].includes(event.action)) {
      const superAdmin = await requireSuperAdmin(openId);
      if (!superAdmin) return { ok: false, code: 'FORBIDDEN', message: '只有超级管理员可操作用户权限' };
      if (event.action === 'listUsers') return { ok: true, users: await listManagedUsers() };
      if (event.action === 'updateUserRole') return await updateManagedUserRole(openId, event);
      return await updateManagedUserEnabled(openId, event);
    }
    return { ok: false, code: 'UNKNOWN_ACTION', message: '未知操作' };
  } catch (error) {
    return { ok: false, code: 'AUTH_ERROR', message: '登录服务暂时不可用，请稍后重试' };
  }
};
