/**
 * 访问后端的统一请求层。
 *
 * 为什么要有这一层？
 *   1. 每个接口都手写一遍 uni.request，会出现大量重复代码（拼地址、带令牌、解析返回、处理错误）；
 *   2. 后端地址以后会变（本地开发 → 线上服务器），集中在这里改一处就行；
 *   3. "登录过期"需要统一处理，不能每个页面各写一遍。
 *
 * 关于"传输方式可切换"：
 *   现在直连本地后端（开发期）。将来部署到线上后，只需把下面的 BASE_URL
 *   换成正式地址，所有调用方（services/*.ts）一行都不用动。
 *   注意 App 端没有"免域名"这种便利：打包上线需要 HTTPS + ICP 备案的域名，
 *   所以从一开始就把地址收在这一处，将来换域名时才不会漏改。
 *
 * 真机调试提示：
 *   127.0.0.1 指的是"运行服务的那台机器"。在微信开发者工具的模拟器里等于你的电脑，
 *   所以能用；但在真机上，手机上的 127.0.0.1 是手机自己，连不到电脑——
 *   而且手机连自己的 localhost 会**拿到非 JSON 的响应**（基座的 webview 服务在监听），
 *   前端于是报「服务端返回格式异常」，这个报错很有迷惑性，别往数据格式上想。
 *
 *   所以真机联调用下面的 DEV_LAN_HOST（电脑的局域网 IP）。
 *   ⚠️ 同时后端必须以 `--host 0.0.0.0` 启动（见 backend/启动后端.bat）——
 *     只绑 127.0.0.1 的话，局域网里谁也连不上，改对 IP 也没用。
 */

import { clearToken, getToken } from '../utils/token';

/**
 * 开发机（跑后端那台电脑）的局域网 IP。
 *
 * 手机真机调试必须用它：手机上的 127.0.0.1 是手机自己。
 * Windows 上用 `ipconfig` 看 WLAN/以太网的 IPv4 地址。
 * ⚠️ 换网络或路由器重新分配后会变（DHCP），变了就改这一行；
 *    想省事可以在路由器里给这台电脑设固定 IP。
 * 2026-09-23：WLAN IP 由 10.100.206.80 变为 10.191.232.80。
 */
const DEV_LAN_HOST = '10.191.232.80';

/**
 * 后端端口。
 *
 * ⚠️ 为什么不是 8000（2026-09-19 踩过）：
 *   **HBuilderX 真机调试时会占用 8000 / 8001**（它自己的内置服务
 *   `launcher/out/service/httpServer.js`）。后端会因此起不来，
 *   而手机连 8000 拿到的是 HBuilderX 返回的纯文本「404」，
 *   前端于是报「服务端返回格式异常」——报错完全指不到真正的原因。
 *   换成 8300 与它隔开，谁先启动都不会撞。
 *   改端口要同时改 backend/启动后端.bat 的 --port。
 */
const DEV_PORT = '8300';

/**
 * 后端接口前缀。改地址只改这一行。
 *
 * 现在统一用局域网 IP：真机走它，H5 也走它（都是"从外面访问这台电脑"），
 * 前提是后端绑 0.0.0.0（见上面的说明）。一个地址覆盖两种调试方式，不用来回切换。
 *
 * 将来上线换成 HTTPS 域名的绝对地址（App 打包需要已备案的域名），所有调用方一行都不用动。
 */
export const BASE_URL = `http://${DEV_LAN_HOST}:${DEV_PORT}/api/v1`;

/** 后端服务根地址（不含 /api/v1）。由 BASE_URL 推导，保证地址仍然只有一处 */
export const API_ORIGIN = BASE_URL.replace(/\/api\/v1$/, '');

/**
 * 把后端返回的**相对文件路径**（如 /uploads/2026/09/xx.png）拼成可直接显示的完整地址。
 *
 * 为什么存相对路径：将来打包 App 或换服务器都要改域名，
 * 只改 BASE_URL 一处，数据库里的存量数据完全不用动。
 * 小程序的 <image> 需要完整地址，所以显示前必须过这一步。
 */
export function resolveFileUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (/^https?:\/\//.test(path)) return path; // 已经是完整地址（比如历史数据）就不动
  return `${API_ORIGIN}${path}`;
}

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
  /**
   * HTTP 方法。
   *
   * ⚠️ 这里刻意没有 PATCH，不是漏写。
   * 微信小程序的 wx.request，官方 method 合法值只有：
   *   OPTIONS / GET / HEAD / POST / PUT / DELETE / TRACE / CONNECT
   * ——**没有 PATCH**，写了也发不出去（不是报错，是静默走不到你想要的分支）。
   *
   * 所以后端虽然按标准语义用 PATCH 做部分更新，也额外开放了一个行为完全一致的
   * POST 入口专供小程序（见 app/api/v1/recipes.py）。
   * 把这个类型补上 'PATCH' 就等于给后来的人埋一个"编译能过、运行时必挂"的坑，
   * 因此宁可让它在类型层面就用不了。
   */
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
