const { callAdminMenu, ensureCurrentShop } = require('../../utils/shop-context');

Page({
  data: {
    loading: true,
    hasAccess: false,
    navigatingTarget: '',
    shopName: '',
    topDishes: [],
    stats: [
      { label: '今日订单', value: '—' },
      { label: '今日营业额', value: '—' },
      { label: '制作中', value: '—' },
      { label: '售罄菜品', value: '—' },
    ],
  },
  onShow() {
    this.setData({ navigatingTarget: '' });
    this.loadAccess();
  },
  async callAdmin(action, payload = {}) {
    return callAdminMenu(action, payload);
  },
  async loadAccess() {
    this.setData({ loading: true });
    try {
      const shop = await ensureCurrentShop();
      const dashboardResult = await this.callAdmin('getTodayDashboard');
      if (dashboardResult.ok && dashboardResult.dashboard) {
        const dashboard = dashboardResult.dashboard;
        this.setData({
          hasAccess: true,
          loading: false,
          shopName: shop.name || '当前店铺',
          topDishes: dashboard.topDishes || [],
          stats: [
            { label: '今日订单', value: String(dashboard.orderCount || 0) },
            { label: '今日营业额', value: `¥${Number(dashboard.revenue || 0).toFixed(2)}` },
            { label: '制作中', value: String(dashboard.makingCount || 0) },
            { label: '售罄菜品', value: String(dashboard.soldOutCount || 0) },
          ],
        });
        return;
      }
      this.setData({ hasAccess: false, loading: false, topDishes: [] });
    } catch (error) {
      wx.showToast({ title: '读取管理数据失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  openDishesPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'dishes' });
    wx.navigateTo({
      url: '/pages/admin-dishes/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开菜品管理失败', icon: 'none' });
      },
    });
  },
  openOrdersPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'orders' });
    wx.navigateTo({
      url: '/pages/admin-orders/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开订单管理失败', icon: 'none' });
      },
    });
  },
  openCategoriesPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'categories' });
    wx.navigateTo({
      url: '/pages/admin-categories/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开分类管理失败', icon: 'none' });
      },
    });
  },
  openShopSettings() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'settings' });
    wx.navigateTo({
      url: '/pages/admin-shop-settings/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开店铺设置失败', icon: 'none' });
      },
    });
  },
});
