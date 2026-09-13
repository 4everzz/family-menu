import { callCloudFunction } from './cloud';

export function callShopAccess(action, payload = {}) {
  return callCloudFunction('shop-access', { action, ...payload });
}

export function joinWithShopCode(code, payload = {}) {
  return callShopAccess('joinWithShopCode', { shopCode: code, ...payload });
}

export function getCurrentShopSnapshot(payload = {}) {
  return callShopAccess('getCurrentShopSnapshot', payload);
}

export function rejoinShop(shopId) {
  return callShopAccess('rejoinShop', { shopId });
}

// 凭本地记住的店铺重新换取通行证（不需要再扫码）。通行证只有 2 小时有效期，
// 过期后由菜单页自动调用它换票，用户不会感知到"失效"。
export function resumeShop(shopId, payload = {}) {
  return callShopAccess('resumeShop', { shopId, ...payload });
}
