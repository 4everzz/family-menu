import { getTempFileURLs } from '../services/cloud';

/** 店铺菜单快照本地缓存：30 天有效期 */
const CACHE_PREFIX = 'uni_family_shop_cache_v1';
const CACHE_TTL = 30 * 24 * 60 * 60 * 1000;
/** 云存储临时链接本身很短命，单独用一个 5 分钟小缓存兜住 */
const TEMP_IMAGE_KEY = 'uni_family_temp_images_v1';
const TEMP_IMAGE_TTL = 5 * 60 * 1000;

interface ShopCacheRecord {
  version: number;
  data: any;
  savedAt: number;
}

interface TempImageRecord {
  url: string;
  savedAt: number;
}

function cacheKey(shopId: any, component: any): string {
  return `${CACHE_PREFIX}:${String(shopId || '')}:${String(component || '')}`;
}

/** 读取店铺快照缓存；过期则顺手清掉并返回 null */
export function readShopCache(shopId: any, component: any): ShopCacheRecord | null {
  const record = uni.getStorageSync(cacheKey(shopId, component)) as ShopCacheRecord | '' | null | undefined;
  if (!record || !record.savedAt || Date.now() - Number(record.savedAt) > CACHE_TTL) {
    if (record) uni.removeStorageSync(cacheKey(shopId, component));
    return null;
  }
  return record;
}

/** 写入店铺快照缓存；写入前先剥掉临时图片链接，避免把会过期的地址存下来 */
export function writeShopCache(shopId: any, component: any, version: any, data: any): void {
  uni.setStorageSync(cacheKey(shopId, component), {
    version: Number(version) || 0,
    data: removeTemporaryImageUrls(data),
    savedAt: Date.now(),
  });
}

/** 主动失效某个店铺快照缓存 */
export function invalidateShopCache(shopId: any, component: any): void {
  uni.removeStorageSync(cacheKey(shopId, component));
}

/** 判断本地缓存记录的版本号是否与云端返回的版本号一致 */
export function isCacheCurrent(record: ShopCacheRecord | null | undefined, version: any): boolean {
  if (!record) return false;
  return Number(record.version) === (Number(version) || 0);
}

/** 剥掉菜品对象上的临时图片链接（imageUrl），只保留可长期存放的 imageFileId */
export function removeTemporaryImageUrls(payload: any): any {
  const dishes = Array.isArray(payload?.dishes) ? payload.dishes : [];
  return {
    ...payload,
    dishes: dishes.map((dish: any) => {
      const { imageUrl, ...safeDish } = dish || {};
      return safeDish;
    }),
  };
}

/** 读取图片临时链接的小缓存 */
function readImages(): Record<string, TempImageRecord> {
  const stored = uni.getStorageSync(TEMP_IMAGE_KEY);
  return stored && typeof stored === 'object' ? (stored as Record<string, TempImageRecord>) : {};
}

/**
 * 刷新菜品图片的临时链接。
 * fileID 换临时 URL 属于有限频/计费操作，所以做了三层保护：
 * 1) 命中未过期的本地小缓存直接复用；
 * 2) 同一次调用内按 fileID 去重；
 * 3) 按每批 50 个分批请求，单批失败不影响其他菜品和下单流程。
 */
export async function refreshDishImageUrls(dishes: any): Promise<any[]> {
  const list = Array.isArray(dishes) ? dishes : [];
  const imageCache = readImages();
  const now = Date.now();
  const ids = [
    ...new Set(
      list.map((dish: any) => String(dish?.imageFileId || '')).filter((id) => id.startsWith('cloud://')),
    ),
  ];
  const urls = new Map<string, string>();
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
      fileList
        .filter((item: any) => item?.status === 0 && item.tempFileURL)
        .forEach((item: any) => {
          urls.set(item.fileID, item.tempFileURL);
          imageCache[item.fileID] = { url: item.tempFileURL, savedAt: Date.now() };
        });
    } catch (error) {
      // 单批图片失败不影响其他菜品和下单。
    }
  }

  uni.setStorageSync(TEMP_IMAGE_KEY, imageCache);
  return list.map((dish: any) => ({
    ...dish,
    imageUrl: urls.get(String(dish?.imageFileId || '')) || dish?.imageUrl || '',
  }));
}
