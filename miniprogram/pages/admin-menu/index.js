const { callAdminMenu, ensureCurrentShop } = require('../../utils/shop-context');

Page({
  data: {
    loading: true,
    hasAccess: false,
    navigatingTarget: '',
    shopName: '',
    canManageMembers: false,
    topDishes: [],
    lastDashboardUpdatedAt: 0,
    loadedAt: 0,
    stats: [
      { label: '今日订单', value: '—' },
      { label: '今日营业额', value: '—' },
      { label: '制作中', value: '—' },
      { label: '售罄菜品', value: '—' },
    ],
  },
  onLoad() {
    this.loadAccess();
  },
  onShow() {
    this.setData({ navigatingTarget: '' });
    const lastChangedAt = Math.max(
      getApp().globalData.menuUpdatedAt || 0,
      getApp().globalData.ordersUpdatedAt || 0,
      getApp().globalData.membersUpdatedAt || 0,
    );
    if (!this.data.loadedAt || lastChangedAt > this.data.lastDashboardUpdatedAt || Date.now() - this.data.loadedAt > 15 * 1000) {
      this.loadAccess();
    }
  },
  async callAdmin(action, payload = {}) {
    return callAdminMenu(action, payload);
  },
  async callShopAdmin(action, payload = {}) {
    const shop = await ensureCurrentShop();
    const response = await wx.cloud.callFunction({
      name: 'shop-admin',
      data: { action, ...payload, shopId: shop.id },
    });
    return response.result || {};
  },
  async loadAccess() {
    if (this.loadingAccess) return this.loadingAccess;
    this.loadingAccess = this.doLoadAccess();
    try {
      return await this.loadingAccess;
    } finally {
      this.loadingAccess = null;
    }
  },
  async doLoadAccess() {
    this.setData({ loading: true });
    try {
      const shop = await ensureCurrentShop();
      const [dashboardResult, memberResult] = await Promise.all([
        this.callAdmin('getTodayDashboard'),
        this.callShopAdmin('listShopMembers').catch(() => ({ ok: false })),
      ]);
      if (dashboardResult.ok && dashboardResult.dashboard) {
        const dashboard = dashboardResult.dashboard;
        this.setData({
          hasAccess: true,
          loading: false,
          shopName: shop.name || '当前店铺',
          canManageMembers: memberResult.ok === true,
          topDishes: dashboard.topDishes || [],
          lastDashboardUpdatedAt: Math.max(
            getApp().globalData.menuUpdatedAt || 0,
            getApp().globalData.ordersUpdatedAt || 0,
            getApp().globalData.membersUpdatedAt || 0,
          ),
          loadedAt: Date.now(),
          stats: [
            { label: '今日订单', value: String(dashboard.orderCount || 0) },
            { label: '今日营业额', value: `¥${Number(dashboard.revenue || 0).toFixed(2)}` },
            { label: '制作中', value: String(dashboard.makingCount || 0) },
            { label: '售罄菜品', value: String(dashboard.soldOutCount || 0) },
          ],
        });
        return;
      }
      this.setData({ hasAccess: false, loading: false, canManageMembers: false, topDishes: [] });
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
  openStatsPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'stats' });
    wx.navigateTo({
      url: '/pages/admin-stats/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开经营报表失败', icon: 'none' });
      },
    });
  },
  openShopMembers() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'members' });
    wx.navigateTo({
      url: '/pages/admin-shop-members/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开成员管理失败', icon: 'none' });
      },
    });
  },
});
