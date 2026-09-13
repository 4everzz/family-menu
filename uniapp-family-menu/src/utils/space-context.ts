/**
 * 家庭组上下文（当前正在查看的家庭组）
 *
 * 这是「契约先行」的过渡实现：
 * 现在只把用户选中的家庭组记在本地缓存里，家庭组列表暂时返回空。
 * 等模块 2 接入后端家庭组接口后，只需要替换本文件的实现，页面无需改动。
 */

/** 本地缓存键：当前选中的家庭组 */
const CURRENT_SPACE_KEY = 'uni_family_current_space';

/** 家庭组信息 */
export interface SpaceInfo {
  /** 家庭组 ID */
  id: string;
  /** 家庭组名称 */
  name: string;
  /** 创建者用户 ID：创建家庭组的人即该家庭的管理员 */
  ownerId?: string;
}

/**
 * 读取当前选中的家庭组
 * @returns 未选择时返回 null
 */
export function getCurrentSpace(): SpaceInfo | null {
  try {
    const raw = uni.getStorageSync(CURRENT_SPACE_KEY);
    if (!raw) return null;
    return typeof raw === 'string' ? (JSON.parse(raw) as SpaceInfo) : (raw as SpaceInfo);
  } catch (error) {
    // 缓存内容损坏时按「未选择」处理，不阻塞页面
    return null;
  }
}

/**
 * 设置当前选中的家庭组
 * @param space 传入 null 表示清空选择
 */
export function setCurrentSpace(space: SpaceInfo | null): void {
  try {
    if (space) uni.setStorageSync(CURRENT_SPACE_KEY, JSON.stringify(space));
    else uni.removeStorageSync(CURRENT_SPACE_KEY);
  } catch (error) {
    // 本地缓存写入失败不影响主流程
  }
}

/** 当前家庭组 ID，未选择时返回空字符串 */
export function getCurrentSpaceId(): string {
  return getCurrentSpace()?.id || '';
}

/** 当前家庭组名称，未选择时返回空字符串 */
export function getCurrentSpaceName(): string {
  return getCurrentSpace()?.name || '';
}

/**
 * 读取当前用户已加入的家庭组列表
 *
 * 当前返回空数组：后端接口尚未提供。
 * 模块 2 接入 FastAPI 后，改为请求真实接口即可，调用方代码不用改。
 */
export async function listMySpaces(): Promise<SpaceInfo[]> {
  return [];
}
