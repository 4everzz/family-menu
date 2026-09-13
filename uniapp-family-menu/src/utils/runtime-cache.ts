/**
 * 运行期内存缓存（不落盘，重启即失效）。
 * 用途：减少同一次会话内重复的云函数请求。
 */

interface CacheRecord {
  data: any;
  savedAt: number;
}

const records: Record<string, CacheRecord> = Object.create(null);
// 并发去重：同一个 key 的请求若还在飞行中，后来者直接复用同一个 Promise
const pendingRequests: Record<string, Promise<any>> = Object.create(null);

/** 读取内存缓存，超过 ttl 毫秒视为失效 */
export function readRuntimeCache(key: string, ttl?: number): any {
  const record = records[key];
  if (!record || Date.now() - record.savedAt > Number(ttl || 0)) return undefined;
  return record.data;
}

/** 写入内存缓存并原样返回数据，方便链式使用 */
export function writeRuntimeCache<T>(key: string, data: T): T {
  records[key] = { data, savedAt: Date.now() };
  return data;
}

/** 清除指定 key 的内存缓存 */
export function clearRuntimeCache(key: string): void {
  delete records[key];
}

/**
 * 带缓存与并发去重的异步加载。
 * force = true 时跳过缓存；同一 key 的并发调用只会真正执行一次 loader。
 */
export async function loadRuntimeCache<T>(
  key: string,
  ttl: number,
  loader: () => Promise<T> | T,
  force = false,
): Promise<T> {
  if (!force) {
    const cached = readRuntimeCache(key, ttl);
    if (cached !== undefined) return cached as T;
  }
  if (pendingRequests[key]) return pendingRequests[key];

  const request = Promise.resolve()
    .then(loader)
    .then((data) => {
      if (data !== undefined && data !== null) writeRuntimeCache(key, data);
      return data;
    })
    .finally(() => {
      delete pendingRequests[key];
    });
  pendingRequests[key] = request;
  return request;
}
