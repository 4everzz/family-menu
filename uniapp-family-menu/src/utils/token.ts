/**
 * 登录令牌（JWT）的本地存取。
 *
 * 为什么单独开一个文件？
 *   令牌是"证明你是谁"的东西，读写的地方越多越容易出错。
 *   统一在这里管理，将来要改存储方式（比如加密、加刷新机制）只改一处。
 *
 * 与旧登录缓存的区别：
 *   这里用的键名是 uni_family_token，与旧的云函数登录缓存分开。
 *   旧的云函数登录还在服务"点菜 / 购物车 / 订单"那几个页面，
 *   新功能用后端令牌，两者暂时并存、互不干扰，等旧页面迁完再合并。
 */

/** 本地缓存键 */
const TOKEN_KEY = 'uni_family_token';

/** 提前量：剩余有效期少于这个值就当作已过期，避免"刚好卡在过期那一刻"的请求失败 */
const EXPIRE_AHEAD_MS = 30 * 1000;

/** 本地保存的令牌内容 */
export interface StoredToken {
  /** 访问令牌本体 */
  token: string;
  /** 过期时间（毫秒时间戳），由签发时的有效期换算而来 */
  expiresAt: number;
}

/**
 * 读取令牌记录
 * @returns 没存过或内容损坏时返回 null
 */
export function getTokenBundle(): StoredToken | null {
  try {
    const raw = uni.getStorageSync(TOKEN_KEY);
    if (!raw) return null;
    const parsed = typeof raw === 'string' ? (JSON.parse(raw) as StoredToken) : (raw as StoredToken);
    if (!parsed || typeof parsed.token !== 'string' || !parsed.token) return null;
    return parsed;
  } catch (error) {
    // 缓存损坏时按"未登录"处理，让上层重新登录，而不是抛错中断页面
    return null;
  }
}

/**
 * 读取令牌字符串
 * @returns 未登录时返回空字符串
 */
export function getToken(): string {
  return getTokenBundle()?.token || '';
}

/**
 * 保存令牌
 * @param token 令牌本体
 * @param expiresInSeconds 有效期（秒），后端登录接口会返回
 */
export function setToken(token: string, expiresInSeconds: number): void {
  const bundle: StoredToken = {
    token,
    expiresAt: Date.now() + expiresInSeconds * 1000,
  };
  try {
    uni.setStorageSync(TOKEN_KEY, JSON.stringify(bundle));
  } catch (error) {
    // 本地写入失败不影响本次会话（内存里仍可用），只是下次启动要重新登录
  }
}

/** 清除令牌（退出登录、或后端返回"登录已过期"时调用） */
export function clearToken(): void {
  try {
    uni.removeStorageSync(TOKEN_KEY);
  } catch (error) {
    // 忽略
  }
}

/** 当前是否持有"尚未过期"的令牌 */
export function hasValidToken(): boolean {
  const bundle = getTokenBundle();
  if (!bundle) return false;
  return bundle.expiresAt - EXPIRE_AHEAD_MS > Date.now();
}
