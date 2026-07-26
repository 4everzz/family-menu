import { API_BASE } from './config.js';
import { auth } from './store.js';

// 统一的接口调用：POST { action, token, ...params } 到 web-admin。
// 约定返回体是 { ok, code?, message?, ...data }。
export async function callApi(action, params = {}, { withToken = true } = {}) {
  const body = { action, ...params };
  if (withToken && auth.token) body.token = auth.token;

  // 给每个请求加 15 秒超时，避免后台/网络卡住时页面一直转圈。
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);

  let response;
  try {
    response = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    if (error && error.name === 'AbortError') {
      return { ok: false, code: 'TIMEOUT', message: '后台响应超时（15秒），请稍后重试或检查云函数' };
    }
    return { ok: false, code: 'NETWORK_ERROR', message: '网络请求失败，请检查后台地址或网络' };
  }
  clearTimeout(timer);

  let data;
  try {
    data = await response.json();
  } catch (error) {
    return { ok: false, code: 'BAD_RESPONSE', message: '后台返回格式异常' };
  }

  // 会话过期：清登录态，让路由守卫把用户送回登录页
  if (data && (data.code === 'SESSION_EXPIRED' || data.code === 'UNAUTHORIZED')) {
    auth.clear();
  }
  return data || { ok: false, code: 'EMPTY', message: '后台无响应' };
}
