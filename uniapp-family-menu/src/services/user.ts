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

import { request, resolveFileUrl } from './http';

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

/**
 * 修改个人资料的请求体。
 *
 * 两个字段都可选：只传哪个就只改哪个（后端用 exclude_unset 区分"没传"和"传 null"）。
 *   · nickname —— 昵称；
 *   · avatarUrl —— 头像**相对路径**（/uploads/...）或 null。
 *     传 null 表示"撤销自定义头像、恢复默认占位图"；不传则保持原值。
 */
export interface UpdateUserPayload {
  nickname?: string;
  /** 头像相对路径或 null（恢复默认）。不传 = 不动头像 */
  avatarUrl?: string | null;
}

/**
 * 修改当前登录用户的个人资料（昵称 / 头像）。
 *
 * 走 **POST** /users/me：这个入口和 PATCH 行为完全一致，后端单独开它是为了兼容
 * 微信小程序（wx.request 不支持 PATCH）。用 POST 而不是 PATCH，前端就能在
 * App / H5 / 小程序三端共用同一段代码——这也正是 http.ts 里 RequestOptions.method
 * 故意不含 PATCH 的原因（见那里的注释）。
 *
 * 后端字段是 snake_case，所以这里手动转一道：前端用 avatarUrl，发过去是 avatar_url。
 */
export async function updateCurrentUser(payload: UpdateUserPayload): Promise<CurrentUser> {
  const data: Record<string, unknown> = {};
  if (payload.nickname !== undefined) data.nickname = payload.nickname;
  if (payload.avatarUrl !== undefined) data.avatar_url = payload.avatarUrl;

  // 后端对"什么都不传"会 422 拒绝；这里前置拦截，避免白打一次请求
  if (Object.keys(data).length === 0) {
    return fetchCurrentUser();
  }

  const dto = await request<UserDto>({ url: '/users/me', method: 'POST', data });
  return {
    id: dto.id,
    username: dto.username || '',
    nickname: dto.nickname || '小家用户',
    avatarUrl: dto.avatar_url || DEFAULT_AVATAR_URL,
  };
}

/**
 * 把头像地址变成 <image> 能直接显示的地址。
 *
 * 两种来源要区别对待：
 *   · 本地打包的占位图（/static/...）—— 是前端资源，直接用它，不能拼服务器地址；
 *   · 服务端上传的相对路径（/uploads/...）—— 必须用 resolveFileUrl 拼成完整地址，
 *     否则在 App / H5 里拼不出真实 URL、图就裂了。
 * 历史数据里若已经是完整 http 地址，resolveFileUrl 会原样返回，不会重复拼。
 *
 * 统一收这一处，是为了避免"编辑页传的是相对路径、我的页却直接拿相对路径显示"
 * 这类只在部分页面裂图的不一致。
 */
export function resolveAvatarUrl(url: string | null | undefined): string {
  if (!url) return DEFAULT_AVATAR_URL;
  if (url.startsWith('/static/')) return url;
  return resolveFileUrl(url);
}
