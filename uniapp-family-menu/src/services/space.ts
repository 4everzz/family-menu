/**
 * 家庭组接口。
 *
 * 字段命名说明：
 *   后端返回的是下划线风格（owner_id、member_count），
 *   前端统一用驼峰（ownerId、memberCount）。
 *   转换集中在这里做，页面代码就不用关心后端的命名习惯，
 *   将来后端改字段名也只需要改这个文件。
 */

import { request } from './http';

/** 后端返回的家庭组结构（原始字段） */
interface SpaceDto {
  id: number;
  name: string;
  owner_id: number;
  member_count: number;
  my_role: string;
  invite_code: string | null;
}

/** 后端返回的成员结构（原始字段） */
interface SpaceMemberDto {
  user_id: number;
  nickname: string;
  avatar_url: string | null;
  role: string;
  is_owner: boolean;
}

/** 家庭组成员角色 */
export type SpaceRole = 'admin' | 'member';

/** 家庭组（前端使用） */
export interface Space {
  /** 家庭组 ID。统一用字符串，方便直接放进本地缓存和页面参数 */
  id: string;
  name: string;
  /** 创建者用户 ID，即管理员 */
  ownerId: number;
  memberCount: number;
  /** 我在这个家庭组里的角色 */
  myRole: SpaceRole;
  /** 邀请码。仅管理员有值，普通成员为 null（由后端控制，不是前端隐藏） */
  inviteCode: string | null;
}

/** 家庭成员 */
export interface SpaceMember {
  userId: number;
  nickname: string;
  /** 微信头像是临时链接，会过期，不适合长期展示 */
  avatarUrl: string | null;
  role: SpaceRole;
  /** 是否是创建者（管理员） */
  isOwner: boolean;
}

/** 把后端字段转成前端结构 */
function toSpace(dto: SpaceDto): Space {
  return {
    id: String(dto.id),
    name: dto.name,
    ownerId: dto.owner_id,
    memberCount: dto.member_count,
    myRole: dto.my_role === 'admin' ? 'admin' : 'member',
    inviteCode: dto.invite_code,
  };
}

/** 我创建和加入的全部家庭组 */
export async function fetchMySpaces(): Promise<Space[]> {
  const list = await request<SpaceDto[]>({ url: '/spaces' });
  return list.map(toSpace);
}

/** 后端返回的额度结构（原始字段） */
interface SpaceQuotaDto {
  max_owned: number;
  max_joined: number;
  owned: number;
  joined: number;
}

/** 我在家庭组上的额度用量 */
export interface SpaceQuota {
  /** 最多能创建几个 */
  maxOwned: number;
  /** 最多能加入几个 */
  maxJoined: number;
  /** 已经创建了几个 */
  owned: number;
  /** 已经加入了几个（不含自己创建的） */
  joined: number;
}

/**
 * 读我的家庭组额度。
 *
 * 后端已经把"最多几个"做成了可配置项（将来会员会加次数），
 * 所以前端**不要自己写死 2**——否则后端调了额度、界面还在说 2，
 * 用户就会看到自相矛盾的提示。
 */
export async function fetchSpaceQuota(): Promise<SpaceQuota> {
  const dto = await request<SpaceQuotaDto>({ url: '/spaces/quota' });
  return {
    maxOwned: dto.max_owned,
    maxJoined: dto.max_joined,
    owned: dto.owned,
    joined: dto.joined,
  };
}

/** 创建家庭组，创建者自动成为管理员 */
export async function createSpace(name: string): Promise<Space> {
  const dto = await request<SpaceDto>({ url: '/spaces', method: 'POST', data: { name } });
  return toSpace(dto);
}

/** 用邀请码加入家庭组 */
export async function joinSpace(inviteCode: string): Promise<Space> {
  const dto = await request<SpaceDto>({ url: '/spaces/join', method: 'POST', data: { invite_code: inviteCode } });
  return toSpace(dto);
}

/** 家庭成员列表（调用者必须是该组成员，否则后端返回 403） */
export async function fetchSpaceMembers(spaceId: string): Promise<SpaceMember[]> {
  const list = await request<SpaceMemberDto[]>({ url: `/spaces/${spaceId}/members` });
  return list.map((item) => ({
    userId: item.user_id,
    nickname: item.nickname,
    avatarUrl: item.avatar_url,
    role: item.role === 'admin' ? 'admin' : 'member',
    isOwner: item.is_owner,
  }));
}

/**
 * 退出家庭组。
 *
 * 创建人不能直接退出——后端会返回 400 并提示「请用解散」。
 * 这条规则放在后端是有意的：前端也会按角色隐藏「退出」按钮，但那只是体验，
 * 不是防线（别人绕开界面直接调接口一样要被拦住）。
 */
export async function leaveSpace(spaceId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/leave`, method: 'POST' });
}

/** 把某个成员移出家庭组（只有创建人能操作，后端会校验） */
export async function removeSpaceMember(spaceId: string, userId: number): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}/members/${userId}`, method: 'DELETE' });
}

/**
 * 解散家庭组（只有创建人能操作）。
 *
 * ⚠️ **不可逆**：这个家庭的成员关系、菜谱、菜谱分类都会一起消失。
 * 所以调用方必须先做二次确认，并且在确认文案里明确说清"会删掉什么"——
 * 一句"确定要解散吗"是不够的，用户不知道代价。
 */
export async function dissolveSpace(spaceId: string): Promise<void> {
  await request<null>({ url: `/spaces/${spaceId}`, method: 'DELETE' });
}
