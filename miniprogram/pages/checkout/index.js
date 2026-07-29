const { requireLogin } = require('../../utils/auth-guard');
const { getCartItems, getCartSummary, submitCartOrder } = require('../../utils/cart-store');
const { callAdminMenu } = require('../../utils/shop-context');
const { getCurrentShop } = require('../../utils/shop-store');
const { readShopCache, refreshDishImageUrls, hasMissingDishImageUrls } = require('../../utils/shop-cache');

Page({
  data: {
    loading: true,
    items: [],
    total: '0.00',
    remark: '',
    isSubmitting: false,
  },
  onLoad(options) {
    this.resumeSubmit = options && options.resume === '1';
  },
  async onShow() {
    if (!(await requireLogin())) return;
    await this.renderCheckout();
    if (this.resumeSubmit) {
      this.resumeSubmit = false;
      this.submitOrder();
    }
  },
  async renderCheckout() {
    const rawItems = getCartItems();
    if (!rawItems.length) {
      wx.navigateBack();
      return;
    }
    this.setData({ loading: true });
    try {
      const shop = getCurrentShop();
      const cached = shop ? readShopCache(shop.id, 'menu') : null;
      let dishes = cached && cached.data ? cached.data.dishes : null;
      if (!Array.isArray(dishes)) {
        const result = await callAdminMenu('getCustomerMenu');
        if (!result.ok) {
          const error = new Error(result.message || '读取菜单失败');
          error.code = result.code;
          throw error;
        }
        dishes = result.dishes || [];
      }
      let freshDishes = await refreshDishImageUrls(dishes);
      if (hasMissingDishImageUrls(dishes, freshDishes)) {
        const result = await callAdminMenu('getCustomerMenu');
        if (result.ok) freshDishes = result.dishes || freshDishes;
      }
      const imageUrls = new Map(freshDishes.map((dish) => [dish.id, dish.imageUrl || '']));
      const items = rawItems.map((item) => ({
        ...item,
        imageUrl: imageUrls.get(item.id) || (item.imageFileId ? '' : (item.imageUrl || '')),
      }));
      const summary = getCartSummary();
      this.setData({ items, total: summary.total, remark: getApp().globalData.checkoutRemark || '' });
    } catch (error) {
      if (this.shouldConfirmTable(error.code, error.message)) {
        this.goToTableEntry();
        return;
      }
      const summary = getCartSummary();
      this.setData({ items: rawItems, total: summary.total, remark: getApp().globalData.checkoutRemark || '' });
    } finally {
      this.setData({ loading: false });
    }
  },
  shouldConfirmTable(code, message) {
    return ['TABLE_REQUIRED', 'TABLE_NOT_AVAILABLE', 'INVALID_TABLE'].includes(code)
      || String(message || '').includes('桌码');
  },
  goToTableEntry() {
    wx.showModal({
      title: '请先扫码确认桌位',
      content: '请回到点餐页，点击右上角“扫码”确认桌码后再提交订单。',
      showCancel: false,
      success: () => wx.switchTab({ url: '/pages/menu/index' }),
    });
  },
  updateRemark(event) {
    const remark = event.detail.value;
    getApp().globalData.checkoutRemark = remark;
    this.setData({ remark });
  },
  continueOrdering() {
    wx.navigateBack();
  },
  async submitOrder() {
    if (this.data.isSubmitting || !(await requireLogin())) return;
    this.setData({ isSubmitting: true });
    try {
      const result = await submitCartOrder(this.data.remark);
      if (!result.ok || !result.order) {
        if (this.shouldConfirmTable(result.code, result.message)) {
          this.goToTableEntry();
          return;
        }
        const dishNames = Array.isArray(result.dishNames) && result.dishNames.length ? result.dishNames.join('、') : '菜品';
        const message = result.code === 'OUT_OF_STOCK' ? `${dishNames}库存不足，请调整数量后重试` : (result.message || '提交订单失败');
        throw new Error(message);
      }
      getApp().globalData.checkoutRemark = '';
      wx.showToast({ title: '订单已提交', icon: 'success' });
      setTimeout(() => wx.switchTab({ url: '/pages/orders/index' }), 500);
    } catch (error) {
      wx.showToast({ title: error.message || '提交失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
});
