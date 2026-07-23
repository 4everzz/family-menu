const CURRENT_SHOP_KEY = 'current_shop_context';

function getCurrentShop() {
  const app = getApp();
  return app.globalData.currentShop || wx.getStorageSync(CURRENT_SHOP_KEY) || null;
}

function setCurrentShop(shop) {
  const normalized = {
    id: String(shop && shop.id || ''),
    name: String(shop && shop.name || ''),
    role: String(shop && shop.role || 'customer'),
    orderEntryMode: String(shop && shop.orderEntryMode || 'store_entry'),
  };
  if (!normalized.id || !normalized.name) return false;
  const app = getApp();
  const previous = getCurrentShop();
  if (previous && previous.id && previous.id !== normalized.id) {
    app.globalData.cart = [];
    app.saveCart();
  }
  app.globalData.currentShop = normalized;
  wx.setStorageSync(CURRENT_SHOP_KEY, normalized);
  return true;
}

module.exports = {
  getCurrentShop,
  setCurrentShop,
};
