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
    cartTotal: '0',
    selectedDish: null,
    selectedSpicy: '正常辣',
    quickRemarkOptions: [
      { label: '少油', selected: false },
      { label: '少盐', selected: false },
    ],
    customRemark: '',
  },
  onShow() {
    this.renderDishes();
  },
  selectCategory(event) {
    this.setData({ activeCategory: event.currentTarget.dataset.id }, () => this.renderDishes());
  },
  addDish(event) {
    const id = event.currentTarget.dataset.id;
    const dish = dishes.find((item) => item.id === id);
    this.addCartItem(dish, ['正常辣']);
    this.renderDishes();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },
  openDish(event) {
    const dish = dishes.find((item) => item.id === event.currentTarget.dataset.id);
    if (!dish) return;
    this.setData({
      selectedDish: dish,
      selectedSpicy: '正常辣',
      quickRemarkOptions: this.data.quickRemarkOptions.map((item) => ({ ...item, selected: false })),
      customRemark: '',
    });
  },
  closeDish() {
    this.setData({ selectedDish: null });
  },
  stopModalPropagation() {},
  selectDetailSpicy(event) {
    this.setData({ selectedSpicy: event.currentTarget.dataset.value });
  },
  toggleQuickRemark(event) {
    const value = event.currentTarget.dataset.value;
    const quickRemarkOptions = this.data.quickRemarkOptions.map((item) => (
      item.label === value ? { ...item, selected: !item.selected } : item
    ));
    this.setData({ quickRemarkOptions });
  },
  updateCustomRemark(event) {
    this.setData({ customRemark: event.detail.value });
  },
  addSelectedDish() {
    const { selectedDish, selectedSpicy, quickRemarkOptions, customRemark } = this.data;
    if (!selectedDish) return;
    const options = [selectedSpicy];
    quickRemarkOptions.filter((item) => item.selected).forEach((item) => options.push(item.label));
    if (customRemark.trim()) options.push(`备注：${customRemark.trim()}`);
    this.addCartItem(selectedDish, options);
    this.closeDish();
    this.renderDishes();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },
  addCartItem(dish, options) {
    const app = getApp();
    const cartKey = `${dish.id}|${options.join('|')}`;
    const cartItem = app.globalData.cart.find((item) => (item.cartKey || `${item.id}|${(item.options || ['正常辣']).join('|')}`) === cartKey);
    if (cartItem) {
      cartItem.quantity += 1;
      return;
    }
    app.globalData.cart.push({ ...dish, cartKey, options, quantity: 1 });
  },
  goCart() {
    wx.navigateTo({ url: '/pages/cart/index' });
  },
  renderDishes() {
    const app = getApp();
    const filtered = this.data.activeCategory === 'all'
      ? dishes
      : dishes.filter((item) => item.category === this.data.activeCategory);
    const rendered = filtered.map((dish) => {
      const quantity = app.globalData.cart
        .filter((item) => item.id === dish.id)
        .reduce((total, item) => total + item.quantity, 0);
      return { ...dish, quantity };
    });
    const cartCount = app.globalData.cart.reduce((total, item) => total + item.quantity, 0);
    const rawTotal = app.globalData.cart.reduce((total, item) => total + item.price * item.quantity, 0);
    const cartTotal = Number.isInteger(rawTotal) ? String(rawTotal) : rawTotal.toFixed(1);
    this.setData({ dishes: rendered, cartCount, cartTotal });
  },
});
