const { clearRuntimeCache, loadRuntimeCache, writeRuntimeCache } = require('./runtime-cache');

const CURRENT_USER_CACHE_KEY = 'current-user';
const CURRENT_USER_CACHE_TTL = 60 * 1000;

async function callAuth(action, payload = {}) {
  const response = await wx.cloud.callFunction({
    name: 'auth',
    data: { action, ...payload },
  });
  return response.result || {};
}

async function refreshCurrentUser(options = {}) {
  const force = options && options.force === true;
  return loadRuntimeCache(CURRENT_USER_CACHE_KEY, CURRENT_USER_CACHE_TTL, async () => {
    try {
      const result = await callAuth('getCurrentUser');
      return result.ok && result.user ? result.user : null;
    } catch (error) {
      return null;
    }
  }, force);
}

function cacheCurrentUser(user) {
  if (user) return writeRuntimeCache(CURRENT_USER_CACHE_KEY, user);
  clearRuntimeCache(CURRENT_USER_CACHE_KEY);
  return null;
}

module.exports = {
  callAuth,
  refreshCurrentUser,
  cacheCurrentUser,
};
