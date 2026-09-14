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
 * 本项目只构建微信小程序（项目决策），这里直接用微信的全局对象 wx。
 * 只声明用到的部分，类型自包含，不依赖 @dcloudio/types 的完整形状。
 */
declare const wx: {
  chooseMedia: (options: {
    count: number;
    mediaType: Array<'image' | 'video'>;
    sourceType?: Array<'album' | 'camera'>;
    success?: (res: { tempFiles?: Array<{ tempFilePath?: string }> }) => void;
    fail?: (err: { errMsg?: string }) => void;
  }) => void;
};

/**
 * 从相册选一张图，返回本地临时文件路径。
 *
 * ⚠️ 为什么直接调 wx.chooseMedia 而不是 uni.chooseMedia？
 *   实测本项目这版 uni-app 运行时（3.0.0-5020420260813002）的 mp-weixin 包
 *   **没有实现 chooseMedia 的包装层**（全包 grep 无实现，只有 TS 类型声明），
 *   调 uni.chooseMedia 会抛"chooseMedia is not a function"，
 *   界面上的表现就是「点了没反应」。
 *   直接走 wx.chooseMedia 绕开包装层——它是微信官方 API，基础库 2.10.0 起可用。
 *   若将来要支持 H5/App，这里是必须适配的点之一（和传输适配层同一批）。
 */
export function chooseImageFromAlbum(): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: (res) => {
        const path = res.tempFiles?.[0]?.tempFilePath;
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
