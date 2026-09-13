const CLOUD_ENV = 'cloud1-d2gua37h7753f3812';

let cloudReady = false;

export function initCloud() {
  // #ifdef MP-WEIXIN
  if (!cloudReady && typeof wx !== 'undefined' && wx.cloud) {
    wx.cloud.init({ env: CLOUD_ENV, traceUser: true });
    cloudReady = true;
  }
  // #endif
  return cloudReady;
}

export function callCloudFunction(name, data = {}) {
  initCloud();
  // #ifdef MP-WEIXIN
  return wx.cloud.callFunction({ name, data }).then((response) => response?.result || {});
  // #endif
  return Promise.reject(new Error('当前构建目标不是微信小程序，无法调用微信云函数'));
}

export function getTempFileURLs(fileList = []) {
  initCloud();
  // #ifdef MP-WEIXIN
  if (!fileList.length) return Promise.resolve([]);
  return wx.cloud.getTempFileURL({ fileList }).then((response) => response?.fileList || []);
  // #endif
  return Promise.resolve([]);
}
