const { dishes } = require('../../data/menu');

Page({
  data: {
    categories: [
      { id: 'all', name: '全部' },
      { id: 'recommended', name: '推荐' },
      { id: 'home', name: '家常菜' },
      { id: 'soup', name: '汤品' },
      { id: 'staple', name: '主食' },
    ],
    activeCategory: 'all',
    dishes: [],
    cartCount: 0,
  },
  onShow() {
    this.renderDishes();
  },
  selectCategory(event) {
    this.setData({ activeCategory: event.currentTarget.dataset.id }, () => this.renderDishes());
  },
  addDish(event) {
    const id = event.currentTarget.dataset.id;
    const app = getApp();
    const dish = dishes.find((item) => item.id === id);
    const cartItem = app.globalData.cart.find((item) => item.id === id);
    if (cartItem) {
      cartItem.quantity += 1;
    } else {
      app.globalData.cart.push({ ...dish, quantity: 1 });
    }
    this.renderDishes();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },
  openDish(event) {
    wx.navigateTo({ url: `/pages/detail/index?id=${event.currentTarget.dataset.id}` });
  },
  goCart() {
    wx.switchTab({ url: '/pages/cart/index' });
  },
  renderDishes() {
    const app = getApp();
    const filtered = this.data.activeCategory === 'all'
      ? dishes
      : dishes.filter((item) => item.category === this.data.activeCategory);
    const rendered = filtered.map((dish) => {
      const cartItem = app.globalData.cart.find((item) => item.id === dish.id);
      return { ...dish, quantity: cartItem ? cartItem.quantity : 0 };
    });
    const cartCount = app.globalData.cart.reduce((total, item) => total + item.quantity, 0);
    this.setData({ dishes: rendered, cartCount });
  },
});
