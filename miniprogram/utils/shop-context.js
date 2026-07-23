const { getCurrentShop, setCurrentShop } = require('./shop-store');

async function ensureCurrentShop() {
  const currentShop = getCurrentShop();
  if (currentShop && currentShop.id) return currentShop;
  const response = await wx.cloud.callFunction({
    name: 'shop-access',
    data: { action: 'listMyShops' },
  });
  const result = response.result || {};
  const shops = result.ok && Array.isArray(result.shops) ? result.shops : [];
  if (shops.length === 1 && setCurrentShop(shops[0])) return shops[0];
  throw new Error('请通过店铺二维码进入点餐');
}

async function callAdminMenu(action, payload = {}) {
  const shop = await ensureCurrentShop();
  const response = await wx.cloud.callFunction({
    name: 'admin-menu',
    data: { action, ...payload, shopId: shop.id },
  });
  return response.result || {};
}

module.exports = {
  ensureCurrentShop,
  callAdminMenu,
};
