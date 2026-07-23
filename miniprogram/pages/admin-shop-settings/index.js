const { ensureCurrentShop } = require('../../utils/shop-context');

function getChinaDateKey() {
  const chinaTime = new Date(Date.now() + 8 * 60 * 60 * 1000);
  const year = chinaTime.getUTCFullYear();
  const month = String(chinaTime.getUTCMonth() + 1).padStart(2, '0');
  const day = String(chinaTime.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

Page({
  data: {
    loading: true,
    saving: false,
    rotating: false,
    rotateConfirming: false,
    shopName: '',
    acceptingOrders: true,
    closedDates: [],
    selectedDate: getChinaDateKey(),
    latestShopCode: '',
  },
  onShow() {
    this.loadSettings();
  },
  async callShopAdmin(action, payload = {}) {
    const shop = await ensureCurrentShop();
    const response = await wx.cloud.callFunction({
      name: 'shop-admin',
      data: { action, ...payload, shopId: shop.id },
    });
    return response.result || {};
  },
  async loadSettings() {
    this.setData({ loading: true });
    try {
      const result = await this.callShopAdmin('getShopSettings');
      if (!result.ok || !result.settings) throw new Error(result.message || '读取店铺设置失败');
      this.setData({
        loading: false,
        shopName: result.settings.name,
        acceptingOrders: result.settings.acceptingOrders !== false,
        closedDates: result.settings.closedDates || [],
      });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || '读取店铺设置失败', icon: 'none' });
    }
  },
  toggleAcceptingOrders(event) {
    this.setData({ acceptingOrders: event.detail.value === true });
  },
  changeDate(event) {
    this.setData({ selectedDate: event.detail.value });
  },
  addClosedDate() {
    const date = this.data.selectedDate;
    if (this.data.closedDates.includes(date)) {
      wx.showToast({ title: '该日期已在列表中', icon: 'none' });
      return;
    }
    this.setData({ closedDates: [...this.data.closedDates, date].sort() });
  },
  removeClosedDate(event) {
    const date = event.currentTarget.dataset.date;
    this.setData({ closedDates: this.data.closedDates.filter((item) => item !== date) });
  },
  async saveOperatingRules() {
    if (this.data.saving) return;
    this.setData({ saving: true });
    try {
      const result = await this.callShopAdmin('updateOperatingRules', {
        acceptingOrders: this.data.acceptingOrders,
        closedDates: this.data.closedDates,
      });
      if (!result.ok || !result.settings) throw new Error(result.message || '保存失败');
      this.setData({
        acceptingOrders: result.settings.acceptingOrders !== false,
        closedDates: result.settings.closedDates || [],
      });
      wx.showToast({ title: '营业设置已保存', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: error.message || '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },
  rotateShopCode() {
    if (this.data.rotating) return;
    if (!this.data.rotateConfirming) {
      this.setData({ rotateConfirming: true });
      this.rotateTimer = setTimeout(() => this.setData({ rotateConfirming: false }), 8000);
      return;
    }
    if (this.rotateTimer) clearTimeout(this.rotateTimer);
    this.setData({ rotating: true, rotateConfirming: false });
    this.callShopAdmin('rotateShopCode').then((result) => {
      if (!result.ok || !result.shopCode) throw new Error(result.message || '重置店铺码失败');
      this.setData({ rotating: false, latestShopCode: result.shopCode });
      wx.setClipboardData({
        data: result.shopCode,
        success: () => wx.showToast({ title: '新店铺码已复制', icon: 'success' }),
        fail: () => wx.showToast({ title: '请手动保存新店铺码', icon: 'none' }),
      });
    }).catch((error) => {
      wx.showToast({ title: error.message || '重置店铺码失败', icon: 'none' });
      this.setData({ rotating: false, rotateConfirming: false });
    });
  },
  copyLatestShopCode() {
    const shopCode = this.data.latestShopCode;
    if (!shopCode) return;
    wx.setClipboardData({
      data: shopCode,
      success: () => wx.showToast({ title: '店铺码已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }),
    });
  },
  onHide() {
    if (this.rotateTimer) clearTimeout(this.rotateTimer);
    this.rotateTimer = null;
  },
});
