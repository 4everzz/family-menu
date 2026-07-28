const CACHE_PREFIX = 'shop_component_cache_v1';
const CACHE_TTL = 24 * 60 * 60 * 1000;

function makeCacheKey(shopId, component) {
  return `${CACHE_PREFIX}:${String(shopId || '')}:${String(component || '')}`;
}

function readShopCache(shopId, component) {
  const key = makeCacheKey(shopId, component);
  const record = wx.getStorageSync(key);
  if (!record || !record.savedAt || Date.now() - Number(record.savedAt) > CACHE_TTL) {
    if (record) wx.removeStorageSync(key);
    return null;
  }
  return record;
}

function writeShopCache(shopId, component, version, data) {
  if (!shopId || !component) return;
  wx.setStorageSync(makeCacheKey(shopId, component), {
    version: Number(version) || 0,
    data,
    savedAt: Date.now(),
  });
}

function invalidateShopCache(shopId, component) {
  if (!shopId || !component) return;
  wx.removeStorageSync(makeCacheKey(shopId, component));
}

function isCacheCurrent(record, version) {
  return !!record && Number(record.version) === (Number(version) || 0);
}

module.exports = {
  readShopCache,
  writeShopCache,
  invalidateShopCache,
  isCacheCurrent,
};
