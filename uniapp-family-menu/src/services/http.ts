/**
 * 访问后端的统一请求层。
 *
 * 为什么要有这一层？
 *   1. 每个接口都手写一遍 wx.request，会出现大量重复代码（拼地址、带令牌、解析返回、处理错误）；
 *   2. 后端地址以后会变（本地开发 → 微信云托管），集中在这里改一处就行；
 *   3. "登录过期"需要统一处理，不能每个页面各写一遍。
 *
 * 关于"传输方式可切换"：
 *   现在直连本地后端（开发期）。将来部署到微信云托管后，改成 wx.cloud.callContainer，
 *   只需要改 request() 内部的实现，所有调用方（services/space.ts 等）一行都不用动。
 *
 * 真机调试提示：
 *   127.0.0.1 指的是"运行服务的那台机器"。在微信开发者工具的模拟器里等于你的电脑，
 *   所以能用；但在真机上，手机上的 127.0.0.1 是手机自己，连不到电脑。
 *   真机联调需要把下面的地址改成电脑的局域网 IP（例如 http://192.168.1.5:8000/api/v1），
 *   并保证手机和电脑在同一个 WiFi 下。另外开发者工具里要勾选"不校验合法域名"。
 */

import { clearToken, getToken } from '../utils/token';

/** 后端接口前缀。改地址只改这一行 */
const BASE_URL = 'http://127.0.0.1:8000/api/v1';

/** 后端统一返回格式：{ code, message, data } */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

/**
 * 接口错误。
 *
 * 把"HTTP 状态码"和"业务错误码"都带上，
 * 页面既能直接展示 message，也能按 code 做特殊处理。
 */
export class ApiError extends Error {
  /** 业务错误码（后端 code 字段）；网络层失败时为负数 */
  readonly code: number;
  /** HTTP 状态码；连不上服务器时为 0 */
  readonly httpStatus: number;

  constructor(message: string, code: number, httpStatus = 0) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

/** 请求参数 */
export interface RequestOptions {
  /** 接口路径，例如 /spaces */
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: Record<string, unknown>;
  /** 是否携带登录令牌，默认携带；登录接口本身传 false */
  withAuth?: boolean;
}

/**
 * 发起请求。
 * @returns 成功时返回后端 data 字段的内容；失败时抛出 ApiError
 */
export function request<T>(options: RequestOptions): Promise<T> {
  const { url, method = 'GET', data, withAuth = true } = options;

  return new Promise<T>((resolve, reject) => {
    const header: Record<string, string> = { 'Content-Type': 'application/json' };
    if (withAuth) {
      const token = getToken();
      if (token) header.Authorization = `Bearer ${token}`;
    }

    uni.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      header,
      success: (res) => {
        const body = res.data as unknown as ApiResponse<T> | undefined;

        // 登录过期：先把本地令牌清掉，这样下次请求会重新登录，不会一直拿废令牌重试
        if (res.statusCode === 401) {
          clearToken();
          reject(new ApiError(body?.message || '登录已过期，请重新登录', body?.code ?? 1001, 401));
          return;
        }

        // 返回结构不符合约定（例如打到了别的服务上），说明配置有问题，要能看出来
        if (!body || typeof body.code !== 'number') {
          reject(new ApiError('服务端返回格式异常', -1, res.statusCode));
          return;
        }

        if (body.code !== 0) {
          reject(new ApiError(body.message || '请求失败', body.code, res.statusCode));
          return;
        }

        resolve(body.data);
      },
      fail: () => {
        // 最常见的失败就是连不上：后端没启动，或开发者工具没勾选"不校验合法域名"
        reject(new ApiError('无法连接到服务器，请确认后端已启动', -2, 0));
      },
    });
  });
}
