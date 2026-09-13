/**
 * 本地缓存读写封装。
 * 统一吞掉异常并返回默认值，避免小程序端 storage 异常导致页面白屏。
 */

/** 读取本地缓存；取不到、为空串或 null 时返回 fallback */
export function getStorage<T = any>(key: string, fallback: T | null = null): T | null {
  try {
    const value = uni.getStorageSync(key);
    return value === '' || value === undefined || value === null ? fallback : (value as T);
  } catch (error) {
    return fallback;
  }
}

/** 写入本地缓存，返回是否成功（不向外抛异常） */
export function setStorage(key: string, value: any): boolean {
  try {
    uni.setStorageSync(key, value);
    return true;
  } catch (error) {
    return false;
  }
}

/** 删除本地缓存，返回是否成功（不向外抛异常） */
export function removeStorage(key: string): boolean {
  try {
    uni.removeStorageSync(key);
    return true;
  } catch (error) {
    return false;
  }
}
