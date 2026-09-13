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
