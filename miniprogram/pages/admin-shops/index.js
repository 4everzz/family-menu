const { setCurrentShop } = require('../../utils/shop-store');

Page({
  data: {
    loading: true,
    creating: false,
    shops: [],
    name: '',
  },
  onShow() {
    this.loadShops();
  },
  async callShopAdmin(action, payload = {}) {
    const response = await wx.cloud.callFunction({
      name: 'shop-admin',
      data: { action, ...payload },
    });
    return response.result || {};
  },
  async loadShops() {
    this.setData({ loading: true });
    try {
      const result = await this.callShopAdmin('listShops');
      if (!result.ok) throw new Error(result.message || '读取店铺失败');
      this.setData({ loading: false, shops: result.shops || [] });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || '读取店铺失败', icon: 'none' });
    }
  },
  updateName(event) {
    this.setData({ name: String(event.detail.value || '').slice(0, 20) });
  },
  async createShop() {
    if (this.data.creating) return;
    const name = this.data.name.trim();
    if (!name) {
      wx.showToast({ title: '请填写店铺名称', icon: 'none' });
      return;
    }
    this.setData({ creating: true });
    try {
      const result = await this.callShopAdmin('createShop', { name });
      if (!result.ok || !result.shop) throw new Error(result.message || '创建店铺失败');
      setCurrentShop(result.shop);
      this.setData({ name: '' });
      if (result.initialShopCode) {
        wx.setClipboardData({
          data: result.initialShopCode,
          success: () => wx.showToast({ title: '店铺码已复制', icon: 'success' }),
        });
      }
      await this.loadShops();
    } catch (error) {
      wx.showToast({ title: error.message || '创建店铺失败', icon: 'none' });
    } finally {
      this.setData({ creating: false });
    }
  },
  openShopManagement(event) {
    const shop = event.currentTarget.dataset.shop;
    if (!shop || !setCurrentShop(shop)) return;
    wx.navigateTo({ url: '/pages/admin-menu/index' });
  },
});
