Page({
  data: {
    items: [],
    total: '0.00',
    isSubmitting: false,
    remark: '',
  },
  onShow() {
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
  submitOrder() {
    const app = getApp();
    if (this.data.isSubmitting) return;
    if (!app.globalData.cart.length) {
      wx.showToast({ title: '请先选择菜品', icon: 'none' });
      return;
    }
    this.setData({ isSubmitting: true });
    const total = app.globalData.cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const order = {
      id: `HJ${Date.now().toString().slice(-8)}`,
      status: '制作中',
      statusNote: '订单已提交，正在制作中',
      total: total.toFixed(2),
      createdAt: new Date().toLocaleString(),
      items: app.globalData.cart.map((item) => ({ ...item })),
      summary: app.globalData.cart.map((item) => `${item.name} × ${item.quantity}`).join('、'),
      remark: this.data.remark.trim(),
    };
    app.globalData.orders.unshift(order);
    app.saveOrders();
    app.globalData.cart = [];
    this.setData({ remark: '' });
    wx.showToast({ title: '订单已提交', icon: 'success' });
    setTimeout(() => {
      this.setData({ isSubmitting: false });
      wx.switchTab({ url: '/pages/orders/index' });
    }, 500);
  },
  changeQuantity(cartKey, delta) {
    const app = getApp();
    const item = app.globalData.cart.find((cartItem) => (cartItem.cartKey || `${cartItem.id}|${(cartItem.options || ['正常辣']).join('|')}`) === cartKey);
    if (!item) return;
    item.quantity += delta;
    app.globalData.cart = app.globalData.cart.filter((cartItem) => cartItem.quantity > 0);
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
