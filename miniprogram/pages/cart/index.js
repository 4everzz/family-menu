const { requireLogin } = require('../../utils/auth-guard');

Page({
  data: {
    items: [],
    total: '0.00',
    isSubmitting: false,
    remark: '',
  },
  async onShow() {
    if (!(await requireLogin())) return;
    this.renderCart();
  },
  increase(event) {
    this.changeQuantity(event.currentTarget.dataset.key, 1);
  },
  decrease(event) {
    this.changeQuantity(event.currentTarget.dataset.key, -1);
  },
  updateRemark(event) {
    this.setData({ remark: event.detail.value });
  },
  clearCart() {
    if (this.data.isSubmitting || !this.data.items.length) return;
    wx.showModal({
      title: '清空购物车',
      content: '确定移除当前已选的全部菜品吗？',
      confirmText: '清空',
      confirmColor: '#DC2626',
      success: (result) => {
        if (!result.confirm) return;
        const app = getApp();
        app.globalData.cart = [];
        app.saveCart();
        this.setData({ remark: '' });
        this.renderCart();
        wx.showToast({ title: '购物车已清空', icon: 'success' });
      },
    });
  },
  async submitOrder() {
    const app = getApp();
    if (this.data.isSubmitting) return;
    if (!(await requireLogin())) return;
    if (!app.globalData.cart.length) {
      wx.showToast({ title: '请先选择菜品', icon: 'none' });
      return;
    }
    this.setData({ isSubmitting: true });
    try {
      const response = await wx.cloud.callFunction({
        name: 'admin-menu',
        data: {
          action: 'createOrder',
          items: app.globalData.cart.map((item) => ({ id: item.id, quantity: item.quantity, options: item.options || [] })),
          remark: this.data.remark.trim(),
        },
      });
      const result = response.result || {};
      if (!result.ok || !result.order) {
        const dishNames = Array.isArray(result.dishNames) && result.dishNames.length
          ? result.dishNames.join('、')
          : '该菜品';
        const message = result.code === 'OUT_OF_STOCK'
          ? `${dishNames}库存不足，请调整数量后重试`
          : (result.message || '提交订单失败');
        throw new Error(message);
      }
      app.globalData.orders.unshift(result.order);
      app.saveOrders();
      app.globalData.cart = [];
      app.saveCart();
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({ remark: '' });
      wx.showToast({ title: '订单已提交', icon: 'success' });
      setTimeout(() => wx.switchTab({ url: '/pages/orders/index' }), 500);
    } catch (error) {
      wx.showToast({ title: error.message || '提交失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
  changeQuantity(cartKey, delta) {
    const app = getApp();
    const item = app.globalData.cart.find((cartItem) => (cartItem.cartKey || `${cartItem.id}|${(cartItem.options || ['正常辣']).join('|')}`) === cartKey);
    if (!item) return;
    item.quantity += delta;
    app.globalData.cart = app.globalData.cart.filter((cartItem) => cartItem.quantity > 0);
    app.saveCart();
    this.renderCart();
  },
  renderCart() {
    const cart = getApp().globalData.cart;
    const items = cart.map((item) => ({
      ...item,
      cartKey: item.cartKey || `${item.id}|${(item.options || ['正常辣']).join('|')}`,
      optionsText: (item.options || []).join(' · '),
    }));
    const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    this.setData({ items, total: total.toFixed(2) });
  },
});
