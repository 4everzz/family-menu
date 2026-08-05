const { callAdminMenu } = require('./shop-context');
const { getCurrentShop } = require('./shop-store');
const { invalidateShopCache } = require('./shop-cache');
const { invalidateMyOrders } = require('./order-store');

function getCartKey(item) {
  return item.cartKey || `${item.id}|${(item.options || []).join('|')}`;
}

function getOrderRequestId() {
  const app = getApp();
  if (!app.globalData.orderRequestId) {
    app.globalData.orderRequestId = `order_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
  }
  return app.globalData.orderRequestId;
}

function getCartItems() {
  return getApp().globalData.cart.map((item) => ({
    ...item,
    cartKey: getCartKey(item),
    optionsText: (item.options || []).join('、'),
  }));
}

function getCartSummary() {
  const cart = getApp().globalData.cart;
  const count = cart.reduce((total, item) => total + item.quantity, 0);
  const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
  return { count, total: total.toFixed(2) };
}

function changeCartQuantity(cartKey, delta) {
  const app = getApp();
  const item = app.globalData.cart.find((cartItem) => getCartKey(cartItem) === cartKey);
  if (!item) return false;
  item.quantity += delta;
  app.globalData.cart = app.globalData.cart.filter((cartItem) => cartItem.quantity > 0);
  app.saveCart();
  return true;
}

function clearCart() {
  const app = getApp();
  app.globalData.cart = [];
  app.saveCart();
}

async function submitCartOrder(remark) {
  const app = getApp();
  if (!app.globalData.cart.length) return { ok: false, code: 'EMPTY_ORDER', message: '请先选择菜品' };
  const shop = getCurrentShop();
  if (!shop || !shop.tableId) {
    return { ok: false, code: 'TABLE_REQUIRED', message: '请先在点餐页扫码确认桌位后下单' };
  }
  const result = await callAdminMenu('createOrder', {
    items: app.globalData.cart.map((item) => ({ id: item.id, quantity: item.quantity, options: item.options || [] })),
    remark: String(remark || '').trim(),
    requireTable: true,
    tableId: shop.tableId,
    requestId: getOrderRequestId(),
  });
  if (!result.ok || !result.order) return result;
  clearCart();
  invalidateShopCache(shop.id, 'menu');
  invalidateMyOrders();
  app.globalData.menuUpdatedAt = Date.now();
  return result;
}

module.exports = {
  changeCartQuantity,
  clearCart,
  getCartItems,
  getCartSummary,
  submitCartOrder,
};
