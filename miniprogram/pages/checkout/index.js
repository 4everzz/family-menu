const { requireLogin } = require('../../utils/auth-guard');
const { getCartItems, getCartSummary, submitCartOrder } = require('../../utils/cart-store');

Page({
  data: {
    loading: true,
    items: [],
    total: '0.00',
    remark: '',
    isSubmitting: false,
  },
  async onShow() {
    if (!(await requireLogin())) return;
    await this.renderCheckout();
  },
  async renderCheckout() {
    const rawItems = getCartItems();
    if (!rawItems.length) {
      wx.navigateBack();
      return;
    }
    this.setData({ loading: true });
    try {
      const response = await wx.cloud.callFunction({ name: 'admin-menu', data: { action: 'getCustomerMenu' } });
      const result = response.result || {};
      const imageUrls = new Map((result.dishes || []).map((dish) => [dish.id, dish.imageUrl || '']));
      const items = rawItems.map((item) => ({ ...item, imageUrl: imageUrls.get(item.id) || item.imageUrl || '' }));
      const summary = getCartSummary();
      this.setData({ items, total: summary.total, remark: getApp().globalData.checkoutRemark || '' });
    } catch (error) {
      const summary = getCartSummary();
      this.setData({ items: rawItems, total: summary.total, remark: getApp().globalData.checkoutRemark || '' });
    } finally {
      this.setData({ loading: false });
    }
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
