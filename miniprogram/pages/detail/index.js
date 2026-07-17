const { dishes } = require('../../data/menu');

Page({
  data: {
    dish: null,
    spicy: '正常辣',
    lessOil: false,
    extraRice: false,
  },
  onLoad(query) {
    const dish = dishes.find((item) => item.id === query.id);
    if (!dish) {
      wx.showToast({ title: '菜品不存在', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 500);
      return;
    }
    this.setData({ dish });
  },
  selectSpicy(event) {
    this.setData({ spicy: event.currentTarget.dataset.value });
  },
  toggleLessOil() {
    this.setData({ lessOil: !this.data.lessOil });
  },
  toggleExtraRice() {
    this.setData({ extraRice: !this.data.extraRice });
  },
  addToCart() {
    const { dish, spicy, lessOil, extraRice } = this.data;
    if (!dish) return;
    const options = [spicy];
    if (lessOil) options.push('少油');
    if (extraRice) options.push('加饭');
    const cartKey = `${dish.id}|${options.join('|')}`;
    const app = getApp();
    const cart = app.globalData.cart;
    const existing = cart.find((item) => item.cartKey === cartKey);
    if (existing) {
      existing.quantity += 1;
    } else {
      cart.push({ ...dish, cartKey, options, quantity: 1 });
    }
    app.saveCart();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
    setTimeout(() => wx.navigateTo({ url: '/pages/cart/index' }), 500);
  },
});
