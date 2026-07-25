const { getCurrentShop, setCurrentShop } = require('./shop-store');

async function ensureCurrentShop() {
  let currentShop = getCurrentShop();
  if (currentShop && currentShop.id && currentShop.entryToken) return currentShop;
  let shops = [];
  if (currentShop && currentShop.id) {
    shops = [currentShop];
  }
  if (!shops.length) {
    const response = await wx.cloud.callFunction({
      name: 'shop-access',
      data: { action: 'listMyShops' },
    });
    const result = response.result || {};
    shops = result.ok && Array.isArray(result.shops) ? result.shops : [];
  }
  if (shops.length !== 1) throw new Error('当前店铺信息不可用');
  const response = await wx.cloud.callFunction({
    name: 'shop-access',
    data: { action: 'rejoinShop', shopId: shops[0].id },
  });
  const result = response.result || {};
  if (result.ok && result.shop && setCurrentShop(result.shop)) return result.shop;
  throw new Error(result.message || '暂时无法进入当前店铺');
}

async function callAdminMenu(action, payload = {}) {
  const shop = await ensureCurrentShop();
  const response = await wx.cloud.callFunction({
    name: 'admin-menu',
    data: { action, ...payload, shopId: shop.id, entryToken: shop.entryToken || '' },
  });
  return response.result || {};
}

module.exports = {
  ensureCurrentShop,
  callAdminMenu,
};
