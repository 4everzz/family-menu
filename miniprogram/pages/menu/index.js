const { dishes: defaultDishes, categories: defaultCategories } = require('../../data/menu');
const { requireLogin } = require('../../utils/auth-guard');
const { changeCartQuantity, clearCart, getCartItems, getCartSummary } = require('../../utils/cart-store');
const { setCurrentShop, getCurrentShop } = require('../../utils/shop-store');
const { callAdminMenu } = require('../../utils/shop-context');

const SPICE_LEVELS = ['不辣', '微辣', '正常辣', '特辣'];

function readTableCode(value) {
  const candidate = String(value || '').trim().toUpperCase();
  const directCode = candidate.replace(/^TABLE:/, '');
  if (/^[A-Z0-9]{8}$/.test(directCode)) return directCode;
  const match = candidate.match(/(?:^|[?&])TABLECODE=([A-Z0-9]{8})(?:&|$)/);
  return match ? match[1] : '';
}

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
    menuError: '',
    selectedDish: null,
    selectedSpicy: '',
    customRemark: '',
    shopName: '当前店铺',
    tableName: '暂未扫码',
  },
  onLoad() {
    this.updateMenuHeight();
  },
  async onShow() {
    if (!(await requireLogin())) return;
    this.syncTabBar();
    var shop = getCurrentShop();
    if (!shop || !shop.id) {
      try {
        var shopsRes = await wx.cloud.callFunction({ name: 'shop-access', data: { action: 'listMyShops' } });
        var shops = (shopsRes.result && shopsRes.result.ok && shopsRes.result.shops) || [];
        if (shops.length > 0) {
          var joinRes = await wx.cloud.callFunction({ name: 'shop-access', data: { action: 'rejoinShop', shopId: shops[0].id } });
          var joinData = joinRes.result || {};
          if (joinData.ok && joinData.shop) {
            setCurrentShop(joinData.shop);
          }
        }
      } catch (e) {}
    }
    shop = getCurrentShop();
    this.setData({
      shopName: shop && shop.name ? shop.name : '当前店铺',
      tableName: shop && shop.tableName ? shop.tableName : '暂未扫码',
    });
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
    if (!wx.cloud) {
      menuDishes = [];
      this.setData({ categories: [{ id: 'all', name: '全部' }], menuError: '店铺服务未初始化' }, () => this.renderDishes());
      return;
    }
    try {
      const result = await callAdminMenu('getCustomerMenu');
      if (!result.ok) throw new Error(result.message || '菜单读取失败');
      const cloudDishes = Array.isArray(result.dishes) ? result.dishes : [];
      const cloudCategories = Array.isArray(result.categories) ? result.categories : [];
      const spiceCategories = cloudCategories.length ? cloudCategories : defaultCategories;
      const validDishes = cloudDishes.filter((item) => item && item.id && item.name && item.enabled !== false).map((item) => ({
        ...normalizeDishSpiceConfig(item, spiceCategories),
        isSoldOut: item.manualSoldOut === true || (Number.isFinite(Number(item.stock)) && Number(item.stock) <= 0),
      }));
      menuDishes = validDishes;
      const validCategories = cloudCategories.filter((item) => item && item.id && item.name && item.id !== 'all').sort((left, right) => {
        const leftSort = Number.isInteger(left.sort) ? left.sort : Number.MAX_SAFE_INTEGER;
        const rightSort = Number.isInteger(right.sort) ? right.sort : Number.MAX_SAFE_INTEGER;
        return leftSort - rightSort || left.name.localeCompare(right.name, 'zh-CN');
      });
      const categories = validCategories.length
        ? [{ id: 'all', name: '全部' }, ...validCategories]
        : defaultCategories;
      this.setData({ categories, activeCategory: 'all', menuScrollTop: 0, menuError: '' }, () => this.renderDishes());
    } catch (error) {
      menuDishes = [];
      var msg = error.message || '暂时无法读取店铺菜单';
      this.setData({ categories: [{ id: 'all', name: '全部' }], activeCategory: 'all', menuError: msg }, () => this.renderDishes());
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
  updateCustomRemark(event) {
    this.setData({ customRemark: event.detail.value });
  },
  async addSelectedDish() {
    if (!(await requireLogin())) return;
    const { selectedDish, selectedSpicy, customRemark } = this.data;
    if (!selectedDish || selectedDish.isSoldOut) {
      wx.showToast({ title: '该菜品已售罄', icon: 'none' });
      return;
    }
    const options = selectedSpicy ? [selectedSpicy] : [];
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
  goToMyShops() {
    wx.switchTab({ url: '/pages/profile/index' });
  },
  scanTableCodeFromMenu() {
    wx.scanCode({
      success: async (result) => {
        const tableCode = readTableCode(result.result || result.path || '');
        if (!tableCode) {
          wx.showToast({ title: '未识别到桌码', icon: 'none' });
          return;
        }
        wx.showLoading({ title: '确认桌位' });
        try {
          const response = await wx.cloud.callFunction({
            name: 'shop-access',
            data: { action: 'joinWithTableCode', tableCode },
          });
          const data = response.result || {};
          if (!data.ok || !data.shop || !setCurrentShop(data.shop)) throw new Error(data.message || '桌位确认失败');
          this.setData({
            shopName: data.shop.name || this.data.shopName,
            tableName: data.shop.tableName || '暂未扫码',
          });
          await this.loadCloudMenu();
          wx.showToast({ title: `已确认${data.shop.tableName || '桌位'}`, icon: 'success' });
        } catch (error) {
          wx.showToast({ title: error.message || '桌位确认失败', icon: 'none' });
        } finally {
          wx.hideLoading();
        }
      },
      fail: () => wx.showToast({ title: '未完成扫码', icon: 'none' }),
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
      ? categoryDishes.filter((item) => item.name.includes(keyword) || String(item.description || '').includes(keyword))
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
