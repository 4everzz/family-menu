const { dishes: defaultDishes, categories: defaultCategories } = require('../../data/menu');
const { requireLogin } = require('../../utils/auth-guard');
const { changeCartQuantity, clearCart, getCartItems, getCartSummary } = require('../../utils/cart-store');

const SPICE_LEVELS = ['不辣', '微辣', '正常辣', '特辣'];

function normalizeDishSpiceConfig(dish, categories = defaultCategories) {
  const hasExplicitConfig = Array.isArray(dish.spiceOptions);
  const category = categories.find((item) => item.id === dish.category);
  const isSpicyCategory = (category && (category.name === '川菜' || category.name === '湘菜'))
    || dish.category === 'cc' || dish.category === 'cx';
  const spiceOptions = hasExplicitConfig
    ? SPICE_LEVELS.filter((level) => dish.spiceOptions.includes(level))
    : (isSpicyCategory ? SPICE_LEVELS : []);
  const defaultSpice = spiceOptions.includes(dish.defaultSpice)
    ? dish.defaultSpice
    : (spiceOptions.includes('正常辣') ? '正常辣' : (spiceOptions[0] || ''));
  return { ...dish, spiceOptions, defaultSpice };
}

let menuDishes = defaultDishes.map((dish) => normalizeDishSpiceConfig(dish));

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
    cartDrawerOpen: false,
    cartItems: [],
    cartRemark: '',
    selectedDish: null,
    selectedSpicy: '',
    quickRemarkOptions: [
      { label: '少油', selected: false },
      { label: '少盐', selected: false },
    ],
    customRemark: '',
  },
  onLoad() {
    this.updateMenuHeight();
  },
  async onShow() {
    if (!(await requireLogin())) return;
    this.syncTabBar();
    await this.loadCloudMenu();
    this.renderDishes();
  },
  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 0 });
  },
  onResize() {
    this.updateMenuHeight();
  },
  getMenuHeight(cartCount = this.data.cartCount) {
    const { windowHeight, windowWidth } = wx.getSystemInfoSync();
    const rpxPerPixel = 750 / windowWidth;
    const cartReservedHeight = cartCount > 0 ? 120 : 0;
    return Math.max(520, Math.floor(windowHeight * rpxPerPixel - 432 - cartReservedHeight));
  },
  updateMenuHeight() {
    const menuHeight = this.getMenuHeight();
    this.setData({ menuHeight });
  },
  async loadCloudMenu() {
    if (!wx.cloud) return;
    try {
      const response = await wx.cloud.callFunction({ name: 'admin-menu', data: { action: 'getCustomerMenu' } });
      const result = response.result || {};
      if (!result.ok) throw new Error(result.message || '菜单读取失败');
      const cloudDishes = Array.isArray(result.dishes) ? result.dishes : [];
      const cloudCategories = Array.isArray(result.categories) ? result.categories : [];
      const spiceCategories = cloudCategories.length ? cloudCategories : defaultCategories;
      const validDishes = cloudDishes.filter((item) => item && item.id && item.name && item.enabled !== false).map((item) => ({
        ...normalizeDishSpiceConfig(item, spiceCategories),
        isSoldOut: item.manualSoldOut === true || (Number.isFinite(Number(item.stock)) && Number(item.stock) <= 0),
      }));
      if (!validDishes.length) return;
      menuDishes = validDishes;
      const validCategories = cloudCategories.filter((item) => item && item.id && item.name && item.id !== 'all').sort((left, right) => {
        const leftSort = Number.isInteger(left.sort) ? left.sort : Number.MAX_SAFE_INTEGER;
        const rightSort = Number.isInteger(right.sort) ? right.sort : Number.MAX_SAFE_INTEGER;
        return leftSort - rightSort || left.name.localeCompare(right.name, 'zh-CN');
      });
      const categories = validCategories.length
        ? [{ id: 'all', name: '全部' }, ...validCategories]
        : defaultCategories;
      this.setData({ categories, activeCategory: 'all', menuScrollTop: 0 }, () => this.renderDishes());
    } catch (error) {
      console.warn('云端菜单读取失败，已使用本地菜单', error);
    }
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
  async addDish(event) {
    if (!(await requireLogin())) return;
    const id = event.currentTarget.dataset.id;
    const dish = menuDishes.find((item) => item.id === id);
    if (!dish || dish.isSoldOut) {
      wx.showToast({ title: '该菜品已售罄', icon: 'none' });
      return;
    }
    this.showDishModal(dish);
  },
  openDish(event) {
    const dish = menuDishes.find((item) => item.id === event.currentTarget.dataset.id);
    if (!dish) return;
    this.showDishModal(dish);
  },
  showDishModal(dish) {
    this.setData({
      selectedDish: dish,
      selectedSpicy: dish.defaultSpice || '',
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
  async addSelectedDish() {
    if (!(await requireLogin())) return;
    const { selectedDish, selectedSpicy, quickRemarkOptions, customRemark } = this.data;
    if (!selectedDish || selectedDish.isSoldOut) {
      wx.showToast({ title: '该菜品已售罄', icon: 'none' });
      return;
    }
    const options = selectedSpicy ? [selectedSpicy] : [];
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
    const cartItem = app.globalData.cart.find((item) => (item.cartKey || `${item.id}|${(item.options || []).join('|')}`) === cartKey);
    if (cartItem) {
      cartItem.quantity += 1;
      app.saveCart();
      return;
    }
    app.globalData.cart.push({ ...dish, cartKey, options, quantity: 1 });
    app.saveCart();
  },
  async openCartDrawer() {
    if (!(await requireLogin())) return;
    this.setData({ cartDrawerOpen: true, cartRemark: getApp().globalData.checkoutRemark || this.data.cartRemark });
    this.renderCartDrawer();
  },
  closeCartDrawer() {
    this.setData({ cartDrawerOpen: false });
  },
  stopCartDrawerPropagation() {},
  increaseCartItem(event) {
    if (!changeCartQuantity(event.currentTarget.dataset.key, 1)) return;
    this.renderDishes();
    this.renderCartDrawer();
  },
  decreaseCartItem(event) {
    if (!changeCartQuantity(event.currentTarget.dataset.key, -1)) return;
    if (!getCartSummary().count) this.setData({ cartDrawerOpen: false, cartRemark: '' });
    this.renderDishes();
  },
  updateCartRemark(event) {
    this.setData({ cartRemark: event.detail.value });
  },
  clearCartWithConfirm() {
    if (!this.data.cartItems.length) return;
    wx.showModal({
      title: '清空购物车',
      content: '确定移除当前已选的全部菜品吗？',
      confirmText: '清空',
      confirmColor: '#DC2626',
      success: (result) => {
        if (!result.confirm) return;
        clearCart();
        getApp().globalData.checkoutRemark = '';
        this.setData({ cartDrawerOpen: false, cartRemark: '' });
        this.renderDishes();
      },
    });
  },
  goCheckout() {
    if (!getCartSummary().count) return;
    getApp().globalData.checkoutRemark = this.data.cartRemark;
    this.setData({ cartDrawerOpen: false });
    wx.navigateTo({ url: '/pages/checkout/index' });
  },
  renderCartDrawer() {
    const cartItems = getCartItems().map((item) => {
      const dish = menuDishes.find((candidate) => candidate.id === item.id);
      return { ...item, imageUrl: dish && dish.imageUrl ? dish.imageUrl : (item.imageUrl || '') };
    });
    const summary = getCartSummary();
    this.setData({ cartItems, cartCount: summary.count, cartTotal: summary.total });
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
    const summary = getCartSummary();
    const cartCount = summary.count;
    const cartTotal = summary.total;
    this.setData({ dishes: rendered, cartCount, cartTotal, menuHeight: this.getMenuHeight(cartCount) });
    if (this.data.cartDrawerOpen) this.renderCartDrawer();
  },
});
