/**
 * 登录与注册（对接自己的 FastAPI 后端）。
 *
 * 两条链路，分工不同：
 *   1. 用户名 + 密码 —— **主链路**。App / H5 / 小程序三端行为完全一致，
 *      不依赖任何第三方平台，用户自己注册的账号。
 *   2. 微信小程序静默登录 —— 只有小程序端能用（原因见 loginWithWechat 的注释）。
 *
 * 安全约定：
 *   · 密码只在用户点"提交"的那一刻存在内存里，任何地方都不落盘；
 *   · 令牌存在本地（utils/token.ts），之后每个请求放在 Authorization 头里；
 *   · 后端从令牌解析身份，前端既不需要、也没办法传"我是谁"。
 */

import { ApiError, request } from './http';
import { hasValidToken, setToken } from '../utils/token';

/** 登录页路径。多处引用，抽成常量，避免手写字符串写错一处就悄悄失效 */
export const LOGIN_PATH = '/pages/auth/login';

/** 未登录（与后端 app/core/response.py 的 CODE_UNAUTHORIZED 一致） */
export const CODE_UNAUTHORIZED = 1001;

/** 用户名已被占用（与后端 CODE_USERNAME_TAKEN 一致） */
export const CODE_USERNAME_TAKEN = 1009;

/** 后端返回的用户信息 */
export interface BackendUser {
  id: number;
  /** 老账号（只有微信身份）没有用户名，所以可能为 null */
  username: string | null;
  nickname: string;
  avatar_url: string | null;
}

/** 注册 / 登录接口返回结构 */
export interface LoginResult {
  token: string;
  token_type: string;
  expires_in: number;
  user: BackendUser;
}

/**
 * 提交注册或登录，成功后把令牌存下来。
 *
 * 注册和登录的返回结构完全一致，所以共用这一段；
 * 分开写两份的话，将来返回结构一变就会漏改其中一处。
 */
async function submitCredentials(
  url: string,
  payload: Record<string, unknown>,
): Promise<LoginResult> {
  // withAuth: false —— 这两个接口本来就是用来"换取"令牌的，带着旧令牌没有意义
  const result = await request<LoginResult>({
    url,
    method: 'POST',
    data: payload,
    withAuth: false,
  });
  setToken(result.token, result.expires_in);
  return result;
}

/**
 * 注册一个"用户名 + 密码"的账号。
 *
 * 注册成功后后端会直接返回令牌并进入登录态，用户不需要再输一遍刚设好的密码。
 *
 * ⚠️ 注册**只提交账号信息**，不收昵称、头像：
 *    · 确认密码会一起提交，由后端再比对一次（前端那个确认框只是"提前提示"，
 *      接口是公开的，绕过界面直接调一样能提交，所以真正的闸门必须在服务端）；
 *    · 昵称、头像这些个人资料，等登进去之后去「我的」页改。
 *
 * @param passwordConfirm 再输一遍的密码，必须与 password 一致
 */
export function registerWithPassword(
  username: string,
  password: string,
  passwordConfirm: string,
): Promise<LoginResult> {
  return submitCredentials('/auth/register', {
    username,
    password,
    // 后端字段名是 snake_case，这里保持一致，不做前端驼峰转换——
    // 转换层越少，联调时越不容易因为命名不一致而白排查半天
    password_confirm: passwordConfirm,
  });
}

/** 用"用户名 + 密码"登录 */
export function loginWithPassword(username: string, password: string): Promise<LoginResult> {
  return submitCredentials('/auth/login', { username, password });
}

/**
 * 微信小程序静默登录（仅小程序端）。
 *
 * ⚠️ 这条路**只有微信小程序能用**：
 *   · App 端要接微信登录，得有微信开放平台的「移动应用」，而它要求企业认证
 *     （300 元/年，个人开发者申请不了），所以 App 上没有这条；
 *   · H5 端完全不支持 uni.login。
 * 保留它是因为：小程序里它免登录、免输入，是那个渠道里体验最好的方式；
 * 而且改造前的老账号只有这一条路能进来。
 */
export function loginWithWechat(): Promise<LoginResult> {
  return new Promise<string>((resolve, reject) => {
    uni.login({
      provider: 'weixin',
      success: (res) => {
        // code 只能用一次且 5 分钟过期，所以不能缓存，每次登录都要重新取
        if (res.code) resolve(res.code);
        else reject(new ApiError('未能获取微信登录凭证，请重试', -3, 0));
      },
      fail: () => reject(new ApiError('微信登录失败，请重试', -3, 0)),
    });
  }).then((code) => submitCredentials('/auth/login/wechat', { code }));
}

/** `setCredentials` 的参数。只传要改的字段；不传的保持原值。 */
export interface CredentialsInput {
  /** 新用户名；不传表示不改 */
  username?: string;
  /** 新密码；不传表示不改 */
  password?: string;
  /** 再输一遍新密码，必须与 password 一致 */
  passwordConfirm?: string;
  /** 当前密码。账号**已有密码**时，改任何凭据都必须提供，用来证明是本人 */
  currentPassword?: string;
}

/**
 * 设置 / 修改**自己**的账号凭据（用户名、密码）。返回最新的用户信息。
 *
 * 三种用法（由"传了哪些字段"决定）：
 *   · 只传 password + passwordConfirm + currentPassword → 改密码
 *   · 只传 username + currentPassword                    → 改用户名
 *   · 首次设置（微信登录进来的老账号）→ username + password + passwordConfirm，**不用** currentPassword
 *
 * ⚠️ 身份只从令牌来：**不要**、也没办法传 user_id。
 *    服务端也只认令牌——前端把入口藏起来不是安全边界，别人可以直接调接口。
 *
 * ⚠️ 用 POST 而不是 PATCH：
 *    微信小程序的 `wx.request` 合法 method 里没有 PATCH（见 http.ts 的说明），
 *    后端为此额外开了一个行为完全一致的 POST 入口。这里走的就是那个入口。
 */
export function setCredentials(input: CredentialsInput): Promise<BackendUser> {
  // 只把"真的传了"的字段放进去。
  // ⚠️ 不能图省事写成 `data = {...input}`：那样 username 会以 undefined 出现，
  //    JSON 序列化后变成 null，而后端的语义是"null 表示不改"——
  //    这次正好没事，但只要以后哪个字段用 null 表示"清空"，就会悄悄出问题。
  const data: Record<string, unknown> = {};
  if (input.username !== undefined) data.username = input.username;
  if (input.password !== undefined) data.password = input.password;
  if (input.passwordConfirm !== undefined) data.password_confirm = input.passwordConfirm;
  if (input.currentPassword !== undefined) data.current_password = input.currentPassword;

  return request<BackendUser>({ url: '/auth/me/credentials', method: 'POST', data });
}

/**
 * 当前页面栈里是不是已经有登录页了。
 *
 * 为什么需要这个判断：菜单、冰箱、收藏等页面在取数前都会调 ensureLogin()。
 * 未登录时如果每个页面都无脑 navigateTo 一次，用户点几下功能就会叠出一串登录页，
 * 返回的时候要一层层退回去，很难受。
 */
function isLoginPageOpen(): boolean {
  // getCurrentPages 在各端都可用；万一某个环境没有，也不要因此把取数流程整个打断
  if (typeof getCurrentPages !== 'function') return false;
  const pages = getCurrentPages() as Array<{ route?: string }>;
  return pages.some((page) => (page.route ? `/${page.route}` : '') === LOGIN_PATH);
}

/** 引导到登录页。已经在登录页上就不再压一个新的。 */
function redirectToLogin(): void {
  if (isLoginPageOpen()) return;
  uni.navigateTo({ url: LOGIN_PATH });
}

/**
 * 确保处于登录态，否则引导到登录页并中断当前流程。
 *
 * ⚠️ 语义和改造前不一样了，这是有意的：
 *   以前是"没登录就静默登录"——小程序里能白拿 openid，用户毫无感知。
 *   现在账号是用户自己注册的，服务端没有任何办法凭空知道你是谁，
 *   所以这里只能"发现没登录 → 引导去登录页 → 抛错让调用方停下"，
 *   而不是拿着空令牌去打一堆必然 401 的请求。
 */
export async function ensureLogin(): Promise<void> {
  if (hasValidToken()) return;
  redirectToLogin();
  throw new ApiError('请先登录', CODE_UNAUTHORIZED, 401);
}
