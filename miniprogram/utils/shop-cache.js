// 升级缓存键，自动淘汰曾保存临时图片链接的旧菜单缓存。
const CACHE_PREFIX = 'shop_component_cache_v2';
// 菜单变更由店铺版本号立即失效；30 天仅作为缓存结构升级和异常场景的兜底。
const CACHE_TTL = 30 * 24 * 60 * 60 * 1000;
// 临时图片链接优先保留在内存中；本地仅保存很短时间，避免将可能过期的链接当作永久数据。
const TEMP_IMAGE_URL_TTL = 10 * 60 * 1000;
// 小程序重编译或模拟器短暂重启后，保留很短时间的链接以避免菜单先退回默认图标。
const TEMP_IMAGE_STORAGE_TTL = 5 * 60 * 1000;
const TEMP_IMAGE_STORAGE_KEY = 'dish_temp_image_urls_v1';
const tempImageUrls = new Map();
let persistedTempImageUrls = null;

function readPersistedTempImageUrls() {
  if (persistedTempImageUrls) return persistedTempImageUrls;
  const stored = wx.getStorageSync(TEMP_IMAGE_STORAGE_KEY);
  persistedTempImageUrls = stored && typeof stored === 'object' ? stored : {};
  return persistedTempImageUrls;
}

function getTemporaryImageUrl(fileId, now) {
  const memoryCached = tempImageUrls.get(fileId);
  if (memoryCached && memoryCached.expiresAt > now) return memoryCached.url;

  const stored = readPersistedTempImageUrls()[fileId];
  if (stored && stored.url && now - Number(stored.savedAt || 0) < TEMP_IMAGE_STORAGE_TTL) {
    tempImageUrls.set(fileId, { url: stored.url, expiresAt: now + TEMP_IMAGE_URL_TTL });
    return stored.url;
  }
  return '';
}

function saveTemporaryImageUrls() {
  const now = Date.now();
  const stored = readPersistedTempImageUrls();
  Object.keys(stored).forEach((fileId) => {
    if (!stored[fileId] || now - Number(stored[fileId].savedAt || 0) >= TEMP_IMAGE_STORAGE_TTL) delete stored[fileId];
  });
  wx.setStorageSync(TEMP_IMAGE_STORAGE_KEY, stored);
}

function removeTemporaryImageUrl(fileId) {
  const normalizedId = String(fileId || '').trim();
  if (!normalizedId) return;
  tempImageUrls.delete(normalizedId);
  const stored = readPersistedTempImageUrls();
  if (stored[normalizedId]) {
    delete stored[normalizedId];
    wx.setStorageSync(TEMP_IMAGE_STORAGE_KEY, stored);
  }
}

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

// 云存储临时链接有效期比菜单缓存短，不能写入本地缓存。
function removeTemporaryImageUrls(payload) {
  const dishes = Array.isArray(payload && payload.dishes) ? payload.dishes : [];
  return {
    ...payload,
    dishes: dishes.map((dish) => {
      const { imageUrl, ...safeDish } = dish || {};
      return safeDish;
    }),
  };
}

// 通过云文件 ID 换取新的短期链接；失败时不复用过期链接。
async function refreshDishImageUrls(dishes, options = {}) {
  const list = Array.isArray(dishes) ? dishes : [];
  const fileIds = [...new Set(list.map((dish) => String(dish && dish.imageFileId || '').trim()).filter((id) => id.startsWith('cloud://')))];
  if (!fileIds.length) return list.map((dish) => ({ ...dish, imageUrl: '' }));
  const imageUrls = new Map();
  const now = Date.now();
  const missingFileIds = fileIds.filter((fileId) => {
    const cachedUrl = options.force === true ? '' : getTemporaryImageUrl(fileId, now);
    if (cachedUrl) {
      imageUrls.set(fileId, cachedUrl);
      return false;
    }
    return true;
  });
  let hasNewUrls = false;
  // 云存储临时链接接口单次文件数量有限，按批次请求避免菜品较多时部分图片丢失。
  for (let index = 0; index < missingFileIds.length; index += 50) {
    try {
      const result = await wx.cloud.getTempFileURL({ fileList: missingFileIds.slice(index, index + 50) });
      (result.fileList || []).filter((item) => item.status === 0 && item.tempFileURL)
        .forEach((item) => {
          imageUrls.set(item.fileID, item.tempFileURL);
          tempImageUrls.set(item.fileID, { url: item.tempFileURL, expiresAt: Date.now() + TEMP_IMAGE_URL_TTL });
          readPersistedTempImageUrls()[item.fileID] = { url: item.tempFileURL, savedAt: Date.now() };
          hasNewUrls = true;
        });
    } catch (error) {
      // 单批失败只影响该批图片，其他批次仍可正常展示。
    }
  }
  if (hasNewUrls) saveTemporaryImageUrls();
  return list.map((dish) => ({
    ...dish,
    imageUrl: imageUrls.get(String(dish.imageFileId || '').trim()) || dish.imageUrl || '',
  }));
}

function hasMissingDishImageUrls(sourceDishes, refreshedDishes) {
  const source = Array.isArray(sourceDishes) ? sourceDishes : [];
  const refreshed = Array.isArray(refreshedDishes) ? refreshedDishes : [];
  const expected = source.filter((dish) => String(dish && dish.imageFileId || '').startsWith('cloud://')).length;
  const actual = refreshed.filter((dish) => !!(dish && dish.imageUrl)).length;
  return expected > actual;
}

module.exports = {
  readShopCache,
  writeShopCache,
  invalidateShopCache,
  isCacheCurrent,
  removeTemporaryImageUrls,
  refreshDishImageUrls,
  hasMissingDishImageUrls,
  removeTemporaryImageUrl,
};
