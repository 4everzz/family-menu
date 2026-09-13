/**
 * 登录（对接自己的 FastAPI 后端）。
 *
 * 与 services/auth.js 的关系：
 *   那个是**旧的云函数登录**，服务"点菜 / 购物车 / 订单"那批页面，暂时保持不动；
 *   这个是**新的后端登录**，服务家庭组等新功能。两者并存，等旧页面迁完再合并。
 *
 * 登录流程：
 *   wx.login() 拿到临时 code（不需要用户点授权，静默完成）
 *     → 交给后端换 openid 并签发令牌（AppSecret 只在后端，前端拿不到也存不住）
 *     → 前端只保存令牌，之后每个请求都带 Authorization 头
 *
 * 为什么不能在前端换 openid？
 *   那需要 AppSecret。放在前端等于公开：别人反编译一下就能冒充你的小程序。
 */

import { ApiError, request } from './http';
import { hasValidToken, setToken } from '../utils/token';

/** 后端返回的用户信息 */
export interface BackendUser {
  id: number;
  nickname: string;
  avatar_url: string | null;
}

/** 登录接口返回结构 */
export interface LoginResult {
  token: string;
  token_type: string;
  expires_in: number;
  user: BackendUser;
}

/**
 * 调起微信登录，拿临时凭证 code。
 * 注意：code 只能用一次且 5 分钟过期，所以不能缓存，每次登录都要重新取。
 */
function getWxCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    uni.login({
      provider: 'weixin',
      success: (res) => {
        if (res.code) resolve(res.code);
        else reject(new ApiError('未能获取微信登录凭证，请重试', -3, 0));
      },
      fail: () => reject(new ApiError('微信登录失败，请重试', -3, 0)),
    });
  });
}

/**
 * 走一次完整登录并保存令牌。
 * 首次登录时后端会自动创建用户，前端不需要额外的注册流程。
 */
export async function loginWithWechat(): Promise<LoginResult> {
  const code = await getWxCode();
  const result = await request<LoginResult>({
    url: '/auth/login',
    method: 'POST',
    data: { code },
    withAuth: false,
  });
  setToken(result.token, result.expires_in);
  return result;
}

/**
 * 确保处于已登录状态。
 * 已有未过期令牌时直接返回，不会多打一次接口。
 */
export async function ensureLogin(): Promise<void> {
  if (hasValidToken()) return;
  await loginWithWechat();
}
