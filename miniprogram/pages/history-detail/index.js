Page({
  data: { order: null },
  onLoad(query) {
    const order = getApp().globalData.orders.find((item) => item.id === query.id);
    if (!order) {
      wx.showToast({ title: '订单不存在', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 500);
      return;
    }
    this.setData({
      order: {
        ...order,
        items: (order.items || []).map((item) => ({
          ...item,
          cartKey: item.cartKey || `${item.id}|${(item.options || ['正常辣']).join('|')}`,
          optionsText: (item.options || []).join(' · '),
        })),
      },
    });
  },
  reorder() {
    const { order } = this.data;
    if (!order) return;
    const app = getApp();
    const cart = app.globalData.cart;
    order.items.forEach((dish) => {
      const options = dish.options || ['正常辣'];
      const cartKey = dish.cartKey || `${dish.id}|${options.join('|')}`;
      const existing = cart.find((item) => (item.cartKey || `${item.id}|${(item.options || ['正常辣']).join('|')}`) === cartKey);
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
