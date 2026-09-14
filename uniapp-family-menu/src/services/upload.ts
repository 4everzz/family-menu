/**
 * 图片上传的服务层。
 *
 * 为什么不用统一的 request()？
 *   request() 走 uni.request 发 JSON；上传文件必须走 uni.uploadFile（multipart 表单），
 *   两者是不同的 API。但"拼地址、带令牌、解析 { code, message, data }、识别登录过期"
 *   这些约定必须保持一致——所以这里照着 request() 的规矩手写一遍。
 *
 * 返回的是**相对路径**（如 /uploads/2026/09/xx.png）：
 *   显示时必须先用 http.ts 的 resolveFileUrl() 拼成完整地址，
 *   这是将来打包 App 换域名时唯一要适配的地方。
 */

import { ApiError, BASE_URL, type ApiResponse } from './http';
import { getToken } from '../utils/token';

/**
 * 选图用跨平台的 uni.chooseImage（不是 wx.chooseMedia）：
 *   - App / 微信小程序 / H5 三个目标都有实现，不用为某个平台写专属分支；
 *   - 之前为绕开 mp-weixin 目标里 uni 没包装 chooseMedia 而直接调 wx.chooseMedia，
 *     那是"以小程序为主"时期的妥协——现在 App 是主目标，统一走 uni.* 才对。
 *   - 本项目只传图片，chooseImage 比 chooseMedia 兼容性更好（各平台都支持）。
 */
export function chooseImageFromAlbum(): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    uni.chooseImage({
      count: 1,
      sizeType: ['original', 'compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const path = res.tempFilePaths?.[0];
        if (path) resolve(path);
        else reject(new Error('没有选择图片'));
      },
      fail: (err) => reject(new Error(err?.errMsg || '选图失败')),
    });
  });
}

/** 上传成功后端返回的 data */
export interface UploadResult {
  /** 相对路径。要显示时用 resolveFileUrl() 拼完整地址 */
  url: string;
  /** 文件大小（字节） */
  size: number;
  /** 服务端认定的 MIME 类型（按文件头判断的，不是客户端声称的） */
  contentType: string;
}

/** 上传一张图片（选好图之后调用） */
export function uploadImage(filePath: string): Promise<UploadResult> {
  return new Promise<UploadResult>((resolve, reject) => {
    const token = getToken();
    uni.uploadFile({
      url: `${BASE_URL}/uploads/image`,
      filePath,
      name: 'file',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success: (res) => {
        // uni.uploadFile 的返回体是字符串，要自己解析成 JSON
        try {
          const body = JSON.parse(res.data) as ApiResponse<UploadResult> | undefined;

          if (res.statusCode === 401) {
            reject(new ApiError(body?.message || '登录已过期，请重新登录', body?.code ?? 1001, 401));
            return;
          }
          if (!body || typeof body.code !== 'number') {
            reject(new ApiError('服务端返回格式异常', -1, res.statusCode));
            return;
          }
          if (body.code !== 0) {
            reject(new ApiError(body.message || '上传失败', body.code, res.statusCode));
            return;
          }
          resolve(body.data);
        } catch {
          reject(new ApiError('服务端返回格式异常', -1, res.statusCode));
        }
      },
      fail: () => {
        reject(new ApiError('无法连接到服务器，请确认后端已启动', -2, 0));
      },
    });
  });
}
