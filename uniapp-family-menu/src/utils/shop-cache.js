import { getTempFileURLs } from '../services/cloud';

const CACHE_PREFIX = 'uni_family_shop_cache_v1';
const CACHE_TTL = 30 * 24 * 60 * 60 * 1000;
const TEMP_IMAGE_KEY = 'uni_family_temp_images_v1';
const TEMP_IMAGE_TTL = 5 * 60 * 1000;

function cacheKey(shopId, component) {
  return `${CACHE_PREFIX}:${String(shopId || '')}:${String(component || '')}`;
}

export function readShopCache(shopId, component) {
  const record = uni.getStorageSync(cacheKey(shopId, component));
  if (!record || !record.savedAt || Date.now() - Number(record.savedAt) > CACHE_TTL) {
    if (record) uni.removeStorageSync(cacheKey(shopId, component));
    return null;
  }
  return record;
}

export function writeShopCache(shopId, component, version, data) {
  uni.setStorageSync(cacheKey(shopId, component), {
    version: Number(version) || 0,
    data: removeTemporaryImageUrls(data),
    savedAt: Date.now(),
  });
}

export function invalidateShopCache(shopId, component) {
  uni.removeStorageSync(cacheKey(shopId, component));
}

export function isCacheCurrent(record, version) {
  return Boolean(record) && Number(record.version) === (Number(version) || 0);
}

export function removeTemporaryImageUrls(payload) {
  const dishes = Array.isArray(payload?.dishes) ? payload.dishes : [];
  return {
    ...payload,
    dishes: dishes.map((dish) => {
      const { imageUrl, ...safeDish } = dish || {};
      return safeDish;
    }),
  };
}

function readImages() {
  const stored = uni.getStorageSync(TEMP_IMAGE_KEY);
  return stored && typeof stored === 'object' ? stored : {};
}

export async function refreshDishImageUrls(dishes) {
  const list = Array.isArray(dishes) ? dishes : [];
  const imageCache = readImages();
  const now = Date.now();
  const ids = [...new Set(list.map((dish) => String(dish?.imageFileId || '')).filter((id) => id.startsWith('cloud://')))];
  const urls = new Map();
  const needed = ids.filter((fileID) => {
    const cached = imageCache[fileID];
    if (cached?.url && now - Number(cached.savedAt || 0) < TEMP_IMAGE_TTL) {
      urls.set(fileID, cached.url);
      return false;
    }
    return true;
  });

  for (let index = 0; index < needed.length; index += 50) {
    try {
      const fileList = await getTempFileURLs(needed.slice(index, index + 50));
      fileList.filter((item) => item?.status === 0 && item.tempFileURL).forEach((item) => {
        urls.set(item.fileID, item.tempFileURL);
        imageCache[item.fileID] = { url: item.tempFileURL, savedAt: Date.now() };
      });
    } catch (error) {
      // 单批图片失败不影响其他菜品和下单。
    }
  }
  uni.setStorageSync(TEMP_IMAGE_KEY, imageCache);
  return list.map((dish) => ({
    ...dish,
    imageUrl: urls.get(String(dish?.imageFileId || '')) || dish?.imageUrl || '',
  }));
}
