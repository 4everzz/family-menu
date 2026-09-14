/**
 * 用户接口。
 *
 * 目前只有一个能力：读「当前登录用户」，供设置页显示"现在是谁在登录"。
 *
 * 身份完全由后端从令牌里解析——前端既不传、也传不了用户 ID。
 * 这是有意的：只要能传 ID，别人就能传一个别人的 ID 读到别人的数据。
 */

import { request } from './http';

/** 后端返回的用户结构（原始字段） */
interface UserDto {
  id: number;
  nickname: string;
  avatar_url: string | null;
}

/** 前端使用的用户信息 */
export interface CurrentUser {
  id: number;
  nickname: string;
  avatarUrl: string;
}

/**
 * 读取当前登录用户。
 * 未登录或令牌过期时，统一请求层会抛错（并清掉本地登录态），由调用方处理。
 */
export async function fetchCurrentUser(): Promise<CurrentUser> {
  const dto = await request<UserDto>({ url: '/users/me' });
  return {
    id: dto.id,
    // 微信可能不给昵称（用户没授权过），兜一个可读的默认值，免得界面空着
    nickname: dto.nickname || '微信用户',
    avatarUrl: dto.avatar_url || '',
  };
}
