const { loadMyOrder } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

Page({
  data: { order: null, loading: true },
  async onLoad(query) {
    if (!(await requireLogin())) return;
    let order = null;
    try {
      order = await loadMyOrder(query.id);
    } catch (error) {
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
    if (!order) {
      wx.showToast({ title: '订单不存在', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 500);
      return;
    }
    this.setData({ order, loading: false });
  },
  reorder() {
    const { order } = this.data;
    if (!order) return;
    const app = getApp();
    const cart = app.globalData.cart;
    order.items.forEach((dish) => {
      const options = dish.options || [];
      const cartKey = dish.cartKey || `${dish.id}|${options.join('|')}`;
      const existing = cart.find((item) => (item.cartKey || `${item.id}|${(item.options || []).join('|')}`) === cartKey);
      if (existing) {
        existing.quantity += dish.quantity;
      } else {
        cart.push({ ...dish, cartKey, options, quantity: dish.quantity });
      }
    });
    app.saveCart();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
    setTimeout(() => wx.navigateTo({ url: '/pages/cart/index' }), 400);
  },
});
