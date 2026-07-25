const CURRENT_SHOP_KEY = 'current_shop_context';

function getCurrentShop() {
  const app = getApp();
  return app.globalData.currentShop || null;
}

function setCurrentShop(shop) {
  const role = String(shop && shop.role || 'customer');
  const accessMode = shop && shop.accessMode === 'customer' ? 'customer' : (
    role === 'store_admin' || role === 'super_admin' ? 'staff' : 'customer'
  );
  const normalized = {
    id: String(shop && shop.id || ''),
    name: String(shop && shop.name || ''),
    role,
    orderEntryMode: String(shop && shop.orderEntryMode || 'store_entry'),
    tableId: String(shop && shop.tableId || ''),
    tableName: String(shop && shop.tableName || ''),
    entryToken: accessMode === 'customer' ? String(shop && shop.entryToken || '') : '',
    accessMode,
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

function clearCurrentShop() {
  const app = getApp();
  app.globalData.currentShop = null;
  app.globalData.cart = [];
  app.globalData.checkoutRemark = '';
  app.saveCart();
  wx.removeStorageSync(CURRENT_SHOP_KEY);
}

module.exports = {
  getCurrentShop,
  setCurrentShop,
  clearCurrentShop,
};
