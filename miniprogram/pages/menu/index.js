const { dishes: defaultDishes, categories: defaultCategories } = require('../../data/menu');

let menuDishes = defaultDishes;

Page({
  data: {
    categories: defaultCategories,
    activeCategory: 'all',
    dishes: [],
    keyword: '',
    menuHeight: 900,
    menuScrollTop: 0,
    cloudMenuUpdatedAt: 0,
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
  onLoad() {
    this.updateMenuHeight();
    this.loadCloudMenu();
  },
  onShow() {
    this.syncTabBar();
    this.renderDishes();
    const app = getApp();
    if (this.data.cloudMenuUpdatedAt !== app.globalData.menuUpdatedAt) {
      this.setData({ cloudMenuUpdatedAt: app.globalData.menuUpdatedAt });
      this.loadCloudMenu();
    }
  },
  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 0 });
  },
  onResize() {
    this.updateMenuHeight();
  },
  updateMenuHeight() {
    const { windowHeight, windowWidth } = wx.getSystemInfoSync();
    const rpxPerPixel = 750 / windowWidth;
    const menuHeight = Math.max(520, Math.floor(windowHeight * rpxPerPixel - 432));
    this.setData({ menuHeight });
  },
  async loadCloudMenu() {
    if (!wx.cloud) return;
    try {
      const [cloudDishes, cloudCategories] = await Promise.all([
        this.getCloudRecords('dishes'),
        this.getCloudRecords('categories'),
      ]);
      const validDishes = cloudDishes.filter((item) => item && item.id && item.name && item.enabled !== false).map((item) => ({
        ...item,
        isSoldOut: item.manualSoldOut === true || (Number.isFinite(Number(item.stock)) && Number(item.stock) <= 0),
      }));
      if (!validDishes.length) return;
      menuDishes = validDishes;
      const validCategories = cloudCategories.filter((item) => item && item.id && item.name && item.id !== 'all');
      const categories = validCategories.length
        ? [{ id: 'all', name: '全部' }, ...validCategories]
        : defaultCategories;
      this.setData({ categories, activeCategory: 'all', menuScrollTop: 0 }, () => this.renderDishes());
    } catch (error) {
      console.warn('云端菜单读取失败，已使用本地菜单', error);
    }
  },
  async getCloudRecords(collectionName) {
    const db = wx.cloud.database();
    const pageSize = 20;
    const records = [];
    for (let skip = 0; skip < 100; skip += pageSize) {
      const result = await db.collection(collectionName).skip(skip).limit(pageSize).get();
      records.push(...result.data);
      if (result.data.length < pageSize) break;
    }
    return records;
  },
  selectCategory(event) {
    const menuScrollTop = this.data.menuScrollTop === 0 ? 1 : 0;
    this.setData({ activeCategory: event.currentTarget.dataset.id, menuScrollTop }, () => this.renderDishes());
  },
  updateKeyword(event) {
    this.setData({ keyword: event.detail.value }, () => this.renderDishes());
  },
  clearKeyword() {
    this.setData({ keyword: '' }, () => this.renderDishes());
  },
  addDish(event) {
    const id = event.currentTarget.dataset.id;
    const dish = menuDishes.find((item) => item.id === id);
    if (!dish || dish.isSoldOut) {
      wx.showToast({ title: '该菜品已售罄', icon: 'none' });
      return;
    }
    this.addCartItem(dish, ['正常辣']);
    this.renderDishes();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },
  decreaseDish(event) {
    const id = event.currentTarget.dataset.id;
    const app = getApp();
    const cart = app.globalData.cart;
    const defaultCartKey = `${id}|正常辣`;
    const cartItem = cart.find((item) => item.cartKey === defaultCartKey)
      || cart.find((item) => item.id === id);
    if (!cartItem) return;
    cartItem.quantity -= 1;
    app.globalData.cart = cart.filter((item) => item.quantity > 0);
    app.saveCart();
    this.renderDishes();
  },
  openDish(event) {
    const dish = menuDishes.find((item) => item.id === event.currentTarget.dataset.id);
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
    if (!selectedDish || selectedDish.isSoldOut) {
      wx.showToast({ title: '该菜品已售罄', icon: 'none' });
      return;
    }
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
      app.saveCart();
      return;
    }
    app.globalData.cart.push({ ...dish, cartKey, options, quantity: 1 });
    app.saveCart();
  },
  goCart() {
    wx.navigateTo({ url: '/pages/cart/index' });
  },
  renderDishes() {
    const app = getApp();
    const categoryDishes = this.data.activeCategory === 'all'
      ? menuDishes
      : menuDishes.filter((item) => item.category === this.data.activeCategory);
    const keyword = this.data.keyword.trim();
    const filtered = keyword
      ? categoryDishes.filter((item) => item.name.includes(keyword) || item.description.includes(keyword))
      : categoryDishes;
    const rendered = filtered.map((dish) => {
      const quantity = app.globalData.cart
        .filter((item) => item.id === dish.id)
        .reduce((total, item) => total + item.quantity, 0);
      return { ...dish, quantity, canAdd: !dish.isSoldOut };
    });
    const cartCount = app.globalData.cart.reduce((total, item) => total + item.quantity, 0);
    const rawTotal = app.globalData.cart.reduce((total, item) => total + item.price * item.quantity, 0);
    const cartTotal = Number.isInteger(rawTotal) ? String(rawTotal) : rawTotal.toFixed(1);
    this.setData({ dishes: rendered, cartCount, cartTotal });
  },
});
