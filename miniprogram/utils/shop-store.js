const CURRENT_SHOP_KEY = 'current_shop_context';

function getCurrentShop() {
  const app = getApp();
  return app.globalData.currentShop || null;
}

function setCurrentShop(shop) {
  const role = String(shop && shop.role || 'customer');
  const accessMode = shop && shop.accessMode === 'customer' ? 'customer' : (
    ['manager', 'store_admin', 'store_owner', 'store_staff', 'super_admin'].includes(role) ? 'staff' : 'customer'
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
  const switchedShop = previous && previous.id && previous.id !== normalized.id;
  const changedTable = previous && previous.id === normalized.id && previous.tableId !== normalized.tableId;
  // 同店从未确认桌位变为首次确认桌位时，保留顾客已选菜品。
  const isConfirmingFirstTable = changedTable && !previous.tableId && !!normalized.tableId;
  if (switchedShop || (changedTable && !isConfirmingFirstTable)) {
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
