/**
 * 家庭组上下文（当前正在查看的家庭组）。
 *
 * 为什么需要"当前家庭组"？
 *   一个人可以创建多个家庭组，也可以加入多个家庭组（比如自己家 + 父母家）。
 *   那么从"我的"点进冰箱时，系统必须知道现在看的是哪个家。
 *   切换后，冰箱、菜单这些家庭共享数据都会跟着变。
 *
 * 缓存放什么：
 *   只缓存家庭组的基本信息和 ID，不缓存权限判断结果。
 *   权限永远由后端在每次请求时校验——本地缓存是可以被篡改的，不能当安全依据。
 */

import { fetchMySpaces } from '../services/space';
import type { Space } from '../services/space';

/** 本地缓存键：当前选中的家庭组 */
const CURRENT_SPACE_KEY = 'uni_family_current_space';
/** 最近一次主动切换家庭的提示，供 AI 页面消费。 */
const SPACE_SWITCH_NOTICE_KEY = 'uni_family_space_switch_notice';

/** 家庭组信息 */
export interface SpaceInfo {
  /** 家庭组 ID */
  id: string;
  /** 家庭组名称 */
  name: string;
  /** 创建者用户 ID：创建家庭组的人即该家庭的管理员 */
  ownerId?: number;
  /** 成员数量 */
  memberCount?: number;
  /** 我在这个家庭组里的角色 */
  myRole?: 'admin' | 'member';
  /** 邀请码，仅管理员有值 */
  inviteCode?: string | null;
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

export interface SpaceSwitchNotice {
  fromName: string;
  toName: string;
  fromId?: string;
  toId: string;
  /** 家庭页已经弹过提示时，AI 页只显示分隔线，避免重复弹窗。 */
  toastShown?: boolean;
  createdAt: number;
}

/** 记录一次家庭切换，避免不同页面各自维护一套通知状态。 */
export function recordSpaceSwitch(
  fromName: string,
  to: SpaceInfo,
  fromId?: string,
  toastShown = false,
): void {
  try {
    uni.setStorageSync(
      SPACE_SWITCH_NOTICE_KEY,
      JSON.stringify({
        fromName: fromName || '未选择家庭',
        toName: to.name,
        fromId,
        toId: to.id,
        toastShown,
        createdAt: Date.now(),
      } satisfies SpaceSwitchNotice),
    );
  } catch {
    // 通知只是体验增强，缓存失败不影响家庭切换本身。
  }
}

/** 读取并消费最近一次切换提示，保证同一条提示只显示一次。 */
export function consumeSpaceSwitchNotice(): SpaceSwitchNotice | null {
  try {
    const raw = uni.getStorageSync(SPACE_SWITCH_NOTICE_KEY);
    if (!raw) return null;
    uni.removeStorageSync(SPACE_SWITCH_NOTICE_KEY);
    return typeof raw === 'string'
      ? (JSON.parse(raw) as SpaceSwitchNotice)
      : (raw as SpaceSwitchNotice);
  } catch {
    return null;
  }
}

/** 读取当前用户已加入的家庭组列表（走后端接口） */
export async function listMySpaces(): Promise<SpaceInfo[]> {
  const spaces = await fetchMySpaces();
  // Space 与 SpaceInfo 结构一致，直接返回即可
  return spaces as SpaceInfo[];
}

/**
 * 拉取家庭组列表，并校正"当前家庭组"，返回最新列表。
 *
 * 为什么需要校正？
 *   本地缓存是上一次操作留下的，可能已经失效——比如你被移出了那个家庭组、
 *   或者那个家庭组已经不存在了。这时如果还拿旧 ID 去查冰箱，后端会直接拒绝。
 *   所以每次进页面刷新列表时，顺手检查一次：
 *     - 缓存里的家庭组还在  → 用最新的名称等信息刷新缓存；
 *     - 不在了 / 从没选过   → 自动切到第一个；一个都没有就清空。
 */
export async function resolveCurrentSpace(): Promise<SpaceInfo[]> {
  const spaces = await listMySpaces();

  const currentId = getCurrentSpaceId();
  const matched = spaces.find((item) => item.id === currentId);

  if (matched) {
    setCurrentSpace(matched);
    return spaces;
  }

  setCurrentSpace(spaces[0] ?? null);
  return spaces;
}
