/**
 * 用户接口。
 *
 * 目前有两个能力：
 *   1. 读「当前登录用户」——供「我的」页显示"现在是谁在登录"；
 *   2. 提供默认头像地址——用户还没设过头像时用它占位。
 *
 * 身份完全由后端从令牌里解析——前端既不传、也传不了用户 ID。
 * 这是有意的：只要能传 ID，别人就能传一个别人的 ID 读到别人的数据。
 */

import { request } from './http';

/**
 * 默认头像（进包的本地图片，不依赖网络）。
 *
 * 为什么要有占位图，而不是"没头像就不显示"：
 *   留一片空白会让卡片看起来像加载失败；给一张中性的人形剪影，
 *   用户一眼就懂"这里以后是我的头像"。
 */
export const DEFAULT_AVATAR_URL = '/static/icons/avatar-default.png';

/** 后端返回的用户结构（原始字段） */
interface UserDto {
  id: number;
  username: string | null;
  nickname: string;
  avatar_url: string | null;
}

/** 前端使用的用户信息 */
export interface CurrentUser {
  id: number;
  /** 老账号可能没有用户名（只有微信身份） */
  username: string;
  nickname: string;
  /** 已经处理过兜底：没设头像时就是默认头像的地址，调用方直接拿来用即可 */
  avatarUrl: string;
}

/**
 * 读取当前登录用户。
 *
 * 未登录或令牌过期时，统一请求层会抛错（并清掉本地登录态），由调用方处理。
 */
export async function fetchCurrentUser(): Promise<CurrentUser> {
  const dto = await request<UserDto>({ url: '/users/me' });
  return {
    id: dto.id,
    username: dto.username || '',
    // 兜一个可读的默认值，免得界面空着——注意这里兜底的是"用户自己没填"，不是"后端给不出"
    nickname: dto.nickname || '小家用户',
    avatarUrl: dto.avatar_url || DEFAULT_AVATAR_URL,
  };
}
