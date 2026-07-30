const { dishes: defaultDishes, categories: defaultCategories } = require('../../data/menu');
const { requireLogin } = require('../../utils/auth-guard');
const { changeCartQuantity, clearCart, getCartItems, getCartSummary } = require('../../utils/cart-store');
const { setCurrentShop, getCurrentShop, clearCurrentShop } = require('../../utils/shop-store');
const { callAdminMenu, getCurrentShopSnapshot } = require('../../utils/shop-context');
const { readShopCache, writeShopCache, isCacheCurrent, removeTemporaryImageUrls, refreshDishImageUrls, hasMissingDishImageUrls, removeTemporaryImageUrl } = require('../../utils/shop-cache');

const SPICE_LEVELS = ['不辣', '微辣', '正常辣', '特辣'];

function readEntryCode(value) {
  const candidate = String(value || '').trim().toUpperCase();
  const directCode = candidate.replace(/^(TABLE|SHOP):/, '');
  if (/^[A-Z0-9]{8}$/.test(directCode)) return directCode;
  const match = candidate.match(/(?:^|[?&])(TABLECODE|SHOPCODE|CODE)=([A-Z0-9]{8})(?:&|$)/);
  if (match) return match[2];
  const sceneMatch = candidate.match(/(?:^|[?&])SCENE=(?:TABLE%3A|SHOP%3A)?([A-Z0-9]{8})(?:&|$)/);
  if (sceneMatch) return sceneMatch[1];
  return '';
}

function hasValidShopContext(shop) {
  if (!shop || !shop.id) return false;
  if (shop.accessMode === 'staff') return true;
  return !!shop.entryToken;
}

function getMenuRenderKey(shop, version) {
  return `${String(shop && shop.id || '')}:${Number(version) || 0}`;
}

function isStaffRole(role) {
  return ['manager', 'super_admin', 'store_admin', 'store_owner', 'store_staff'].includes(String(role || ''));
}

function getEntryPromptHeight() {
  const { windowHeight, windowWidth } = wx.getSystemInfoSync();
  const rpxPerPixel = 750 / windowWidth;
  return Math.max(560, Math.floor(windowHeight * rpxPerPixel - 360));
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
    shopName: '暂未进入店铺',
    tableName: '暂未扫码',
    hasShopContext: false,
    canSelectShop: false,
    staffShops: [],
    entryLoading: false,
    entrySwitching: false,
    manualEntryCode: '',
  },
  onLoad() {
    this.updateMenuHeight();
  },
  async onShow() {
    if (this.data.entrySwitching) return;
    const user = await requireLogin();
    if (!user) {
      this.resetEntryState();
      return;
    }
    this.syncTabBar();
    var shop = getCurrentShop();
    const hasShop = hasValidShopContext(shop) && (shop.accessMode !== 'staff' || isStaffRole(shop.role));
    this.setData({
      hasShopContext: hasShop,
      shopName: hasShop && shop.name ? shop.name : '暂未进入店铺',
      tableName: shop && shop.tableName ? shop.tableName : '暂未扫码',
    });
    if (!hasShop) {
      await this.prepareEntryHome(user);
      return;
    }
    const loaded = await this.loadCloudMenu();
    if (!loaded) {
      if (this.shouldClearShopContext()) {
        clearCurrentShop();
        await this.prepareEntryHome(user);
      }
      return;
    }
  },
  resetEntryState() {
    menuDishes = [];
    this.appliedMenuRenderKey = '';
    this.setData({
      hasShopContext: false,
      canSelectShop: false,
      staffShops: [],
      shopName: '暂未进入店铺',
      tableName: '暂未扫码',
      categories: [{ id: 'all', name: '全部' }],
      activeCategory: 'all',
      dishes: [],
      keyword: '',
      menuError: '',
      manualEntryCode: '',
      menuHeight: getEntryPromptHeight(),
      cartDrawerOpen: false,
      selectedDish: null,
    });
    this.renderCartOnly();
  },
  async prepareEntryHome(user) {
    this.resetEntryState();
    this.setData({ entryLoading: true });
    try {
      let shops = [];
      if (user.role === 'super_admin') {
        const response = await wx.cloud.callFunction({ name: 'shop-admin', data: { action: 'listShops' } });
        const result = response.result || {};
        shops = result.ok ? (result.shops || []) : [];
      } else {
        const response = await wx.cloud.callFunction({ name: 'shop-access', data: { action: 'listMyShops' } });
        const result = response.result || {};
        shops = result.ok ? (result.shops || []).filter((item) => isStaffRole(item.role)) : [];
      }
      this.setData({
        canSelectShop: shops.length > 0,
        staffShops: shops.map((item) => ({
          ...item,
          roleText: item.role === 'store_staff' ? '二级管理员' : (item.role === 'super_admin' ? '超级管理员' : '一级管理员'),
        })),
      });
    } catch (error) {
      this.setData({ canSelectShop: false, staffShops: [] });
    } finally {
      this.setData({ entryLoading: false });
    }
  },
  updateManualEntryCode(event) {
    this.setData({ manualEntryCode: String(event.detail.value || '').trim().toUpperCase() });
  },
  async submitManualEntryCode() {
    if (this.data.entrySwitching) return;
    const entryCode = readEntryCode(this.data.manualEntryCode);
    if (!entryCode) {
      wx.showToast({ title: '请输入8位店铺码或桌码', icon: 'none' });
      return;
    }
    await this.enterByEntryCode(entryCode);
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
    const requestId = (this.menuRequestId || 0) + 1;
    this.menuRequestId = requestId;
    const isLatestRequest = () => this.menuRequestId === requestId;
    const shop = getCurrentShop();
    if (!shop || !shop.id) return false;
    if (!wx.cloud) {
      menuDishes = [];
      this.lastMenuErrorCode = 'CLOUD_NOT_INITIALIZED';
      if (isLatestRequest()) this.setData({ menuError: '店铺服务未初始化' });
      return false;
    }
    try {
      // 有本店菜单缓存时先渲染，店铺状态和菜单版本随后在后台核验。
      const cached = readShopCache(shop.id, 'menu');
      const cachedRenderKey = cached ? getMenuRenderKey(shop, cached.version) : '';
      if (cached && cached.data && isLatestRequest()) {
        const cachedPayload = { ...cached.data, dishes: await refreshDishImageUrls(cached.data.dishes) };
        this.applyMenuPayload(cachedPayload, cachedRenderKey);
      }
      const snapshot = await getCurrentShopSnapshot();
      if (!snapshot.ok || !snapshot.access) {
        const error = new Error(snapshot.message || '店铺状态读取失败');
        error.code = snapshot.code || '';
        throw error;
      }
      if (isCacheCurrent(cached, snapshot.access.versions.menu)) {
        let payload = { ...cached.data, dishes: await refreshDishImageUrls(cached.data.dishes) };
        let requiresImageFallback = false;
        // 客户端临时链接换取失败时，由云函数兜底，避免缓存菜单退回默认图标。
        if (hasMissingDishImageUrls(cached.data.dishes, payload.dishes)) {
          const result = await callAdminMenu('getCustomerMenu');
          if (result.ok) {
            payload = { dishes: result.dishes || [], categories: result.categories || [] };
            writeShopCache(shop.id, 'menu', snapshot.access.versions.menu, removeTemporaryImageUrls(payload));
            requiresImageFallback = true;
          }
        }
        if (isLatestRequest()) this.applyMenuPayload(payload, getMenuRenderKey(shop, snapshot.access.versions.menu), requiresImageFallback);
        this.lastMenuErrorCode = '';
        return true;
      }
      const result = await callAdminMenu('getCustomerMenu');
      if (!result.ok) {
        const error = new Error(result.message || '菜单读取失败');
        error.code = result.code || '';
        throw error;
      }
      const payload = {
        dishes: Array.isArray(result.dishes) ? result.dishes : [],
        categories: Array.isArray(result.categories) ? result.categories : [],
      };
      writeShopCache(shop.id, 'menu', snapshot.access.versions.menu, removeTemporaryImageUrls(payload));
      if (isLatestRequest()) this.applyMenuPayload(payload, getMenuRenderKey(shop, snapshot.access.versions.menu));
      this.lastMenuErrorCode = '';
      return true;
    } catch (error) {
      if (!isLatestRequest()) return true;
      this.lastMenuErrorCode = error.code || '';
      const cached = readShopCache(shop.id, 'menu');
      if (cached) {
        this.applyMenuPayload(
          { ...cached.data, dishes: await refreshDishImageUrls(cached.data.dishes) },
          getMenuRenderKey(shop, cached.version),
        );
        wx.showToast({ title: '网络异常，暂显示最近菜单', icon: 'none' });
        return true;
      }
      this.setData({ menuError: error.message || '暂时无法读取店铺菜单' });
      wx.showToast({ title: error.message || '暂时无法读取店铺菜单', icon: 'none' });
      return false;
    }
  },
  applyMenuPayload(payload, renderKey = '', forceRender = false) {
    if (!forceRender && renderKey && this.appliedMenuRenderKey === renderKey) return false;
    const cloudDishes = Array.isArray(payload && payload.dishes) ? payload.dishes : [];
    const cloudCategories = Array.isArray(payload && payload.categories) ? payload.categories : [];
    const spiceCategories = cloudCategories.length ? cloudCategories : defaultCategories;
    menuDishes = cloudDishes.filter((item) => item && item.id && item.name && item.enabled !== false).map((item) => ({
      ...normalizeDishSpiceConfig(item, spiceCategories),
      isSoldOut: item.manualSoldOut === true || (Number.isFinite(Number(item.stock)) && Number(item.stock) <= 0),
    }));
    const validCategories = cloudCategories.filter((item) => item && item.id && item.name && item.id !== 'all').sort((left, right) => {
      const leftSort = Number.isInteger(left.sort) ? left.sort : Number.MAX_SAFE_INTEGER;
      const rightSort = Number.isInteger(right.sort) ? right.sort : Number.MAX_SAFE_INTEGER;
      return leftSort - rightSort || left.name.localeCompare(right.name, 'zh-CN');
    });
    const categories = validCategories.length ? [{ id: 'all', name: '全部' }, ...validCategories] : defaultCategories;
    this.appliedMenuRenderKey = renderKey;
    this.setData({ categories, activeCategory: 'all', menuScrollTop: 0, menuError: '' }, () => this.renderDishes());
    return true;
  },
  shouldClearShopContext() {
    return ['ENTRY_SESSION_REQUIRED', 'ENTRY_SESSION_EXPIRED', 'SHOP_CONTEXT_REQUIRED', 'SHOP_NOT_AVAILABLE', 'SHOP_NOT_FOUND', 'TABLE_NOT_AVAILABLE', 'TABLE_REQUIRED'].includes(this.lastMenuErrorCode);
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
  decreaseDishFromCard(event) {
    if (!changeCartQuantity(event.currentTarget.dataset.key, -1)) return;
    this.renderDishes();
    if (this.data.cartDrawerOpen) this.renderCartDrawer();
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
  scanTableCodeFromMenu() {
    if (this.data.entrySwitching) return;
    this.setData({ entrySwitching: true });
    wx.scanCode({
      success: async (result) => {
        const entryCode = readEntryCode(result.result || result.path || '');
        if (!entryCode) {
          wx.showToast({ title: '未识别到店铺码或桌码', icon: 'none' });
          this.setData({ entrySwitching: false });
          return;
        }
        await this.enterByEntryCode(entryCode, true);
      },
      fail: () => {
        this.setData({ entrySwitching: false });
        wx.showToast({ title: '未完成扫码', icon: 'none' });
      },
    });
  },
  async enterByEntryCode(entryCode, fromScan = false) {
    if (this.data.entrySwitching && !fromScan) return;
    this.setData({ entrySwitching: true });
    wx.showLoading({ title: '进入店铺' });
    try {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('云函数请求超时，请检查网络或云函数部署')), 15000)
      );
      const response = await Promise.race([
        wx.cloud.callFunction({
          name: 'shop-access',
          data: { action: 'joinWithShopCode', shopCode: entryCode },
        }),
        timeoutPromise,
      ]);
      const data = response.result || {};
      if (!data.ok || !data.shop || !setCurrentShop(data.shop)) throw new Error(data.message || '进入店铺失败');
      menuDishes = [];
      this.setData({
        hasShopContext: true,
        manualEntryCode: '',
        shopName: data.shop.name || this.data.shopName,
        tableName: data.shop.tableName || '暂未扫码',
      });
      const loaded = await this.loadCloudMenu();
      if (!loaded) {
        if (this.shouldClearShopContext()) clearCurrentShop();
        return;
      }
      this.renderDishes();
      wx.showToast({ title: `已确认${data.shop.tableName || '店铺'}`, icon: 'success' });
    } catch (error) {
      wx.showToast({ title: error.message || '进入店铺失败', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ entrySwitching: false });
    }
  },
  enterStaffShop(event) {
    const shopId = event.currentTarget.dataset.id;
    if (!shopId || this.data.entryLoading || this.data.entrySwitching) return;
    this.setData({ entryLoading: true, entrySwitching: true });
    wx.cloud.callFunction({
      name: 'shop-access',
      data: { action: 'rejoinShop', shopId },
    }).then(async (response) => {
      const result = response.result || {};
      if (!result.ok || !result.shop || !setCurrentShop(result.shop)) throw new Error(result.message || '进入店铺失败');
      menuDishes = [];
      this.setData({
        hasShopContext: true,
        canSelectShop: false,
        staffShops: [],
        shopName: result.shop.name || '当前店铺',
        tableName: result.shop.tableName || '暂未扫码',
      });
      const loaded = await this.loadCloudMenu();
      if (!loaded) {
        if (this.shouldClearShopContext()) {
          clearCurrentShop();
          const user = await requireLogin();
          if (user) await this.prepareEntryHome(user);
        }
        return;
      }
      this.renderDishes();
    }).catch((error) => {
      wx.showToast({ title: error.message || '进入店铺失败', icon: 'none' });
    }).finally(() => {
      this.setData({ entryLoading: false, entrySwitching: false });
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
  async retryDishImage(event) {
    const id = event.currentTarget.dataset.id;
    const dish = menuDishes.find((item) => item.id === id);
    this.imageRetryCounts = this.imageRetryCounts || {};
    if (!dish || !dish.imageFileId || this.retryingDishImageId === id || this.imageRetryCounts[id] >= 1) return;
    this.imageRetryCounts[id] += 1;
    this.retryingDishImageId = id;
    try {
      removeTemporaryImageUrl(dish.imageFileId);
      const [refreshedDish] = await refreshDishImageUrls([dish], { force: true });
      if (!refreshedDish || !refreshedDish.imageUrl) return;
      menuDishes = menuDishes.map((item) => (item.id === id ? { ...item, imageUrl: refreshedDish.imageUrl } : item));
      delete this.imageRetryCounts[id];
      this.renderDishes();
    } finally {
      this.retryingDishImageId = '';
    }
  },
  renderCartOnly() {
    const summary = getCartSummary();
    this.setData({ cartItems: [], cartCount: summary.count, cartTotal: summary.total });
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
      const dishCartItems = app.globalData.cart.filter((item) => item.id === dish.id);
      const quantity = dishCartItems.reduce((total, item) => total + item.quantity, 0);
      // 卡片减号始终减少最后加入的同菜规格，购物车内仍可按规格精确调整。
      const latestCartItem = dishCartItems.length ? dishCartItems[dishCartItems.length - 1] : null;
      return {
        ...dish,
        quantity,
        canAdd: !dish.isSoldOut,
        canQuickDecrease: !!latestCartItem,
        quickCartKey: latestCartItem ? (latestCartItem.cartKey || `${latestCartItem.id}|${(latestCartItem.options || []).join('|')}`) : '',
      };
    });
    const summary = getCartSummary();
    const cartCount = summary.count;
    const cartTotal = summary.total;
    this.setData({ dishes: rendered, cartCount, cartTotal, menuHeight: this.getMenuHeight(cartCount) });
    if (this.data.cartDrawerOpen) this.renderCartDrawer();
  },
});
