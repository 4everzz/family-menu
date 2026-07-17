Page({
  data: {
    loading: true,
    hasAccess: false,
    openId: '',
    isNavigating: false,
  },
  onLoad() {
    this.loadAccess();
  },
  onShow() {
    this.setData({ isNavigating: false });
  },
  async callAdmin(action, payload = {}) {
    const response = await wx.cloud.callFunction({
      name: 'admin-menu',
      data: { action, ...payload },
    });
    return response.result || {};
  },
  async loadAccess() {
    this.setData({ loading: true });
    try {
      const result = await this.callAdmin('listCategories');
      if (result.ok) {
        this.setData({ hasAccess: true, loading: false });
        return;
      }
      const identity = await this.callAdmin('getIdentity');
      this.setData({ openId: identity.openId || '', hasAccess: false, loading: false });
    } catch (error) {
      wx.showToast({ title: '读取管理数据失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  openDishesPage() {
    if (this.data.isNavigating) return;
    this.setData({ isNavigating: true });
    wx.navigateTo({
      url: '/pages/admin-dishes/index',
      fail: () => {
        this.setData({ isNavigating: false });
        wx.showToast({ title: '打开菜品管理失败', icon: 'none' });
      },
    });
  },
  copyOpenId() {
    if (!this.data.openId) return;
    wx.setClipboardData({ data: this.data.openId });
  },
});
