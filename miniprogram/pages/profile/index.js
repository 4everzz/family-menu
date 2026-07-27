const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');

function getShopRoleText(role) {
  if (role === 'store_owner') return '一级管理员';
  if (role === 'store_staff') return '二级管理员';
  if (role === 'store_admin') return '店铺管理员';
  return '';
}

function getGlobalRoleText(role) {
  if (role === 'super_admin') return '超级管理员';
  if (role === 'manager') return '管理员';
  return '普通用户';
}

Page({
  data: {
    loading: true,
    user: null,
    isManager: false,
  },
  async onShow() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 2 });
    await this.loadCurrentUser();
  },
  async loadCurrentUser() {
    this.setData({ loading: true });
    const user = await refreshCurrentUser();
    if (user && !user.profileCompleted) {
      this.setData({ loading: false });
      wx.navigateTo({ url: '/pages/profile-edit/index' });
      return;
    }
    // 检查用户是否有店铺管理员身份
    let shopRole = '';
    let isShopAdmin = false;
    if (user) {
      try {
        const response = await wx.cloud.callFunction({ name: 'shop-access', data: { action: 'listMyShops' } });
        const result = response.result || {};
        if (result.ok && Array.isArray(result.shops)) {
          const adminShops = result.shops.filter((item) =>
            ['store_admin', 'store_owner', 'store_staff'].includes(String(item.role || ''))
          );
          if (adminShops.length > 0) {
            isShopAdmin = true;
            // 取最高角色
            const roleOrder = { store_owner: 0, store_admin: 0, store_staff: 1 };
            const highest = adminShops.reduce((best, item) =>
              (roleOrder[item.role] || 9) < (roleOrder[best.role] || 9) ? item : best
            , adminShops[0]);
            shopRole = getShopRoleText(highest.role);
          }
        }
      } catch (e) {
        // 忽略加载失败
      }
    }
    const displayRole = shopRole || getGlobalRoleText(user ? user.role : '');
    const profileUser = user ? {
      ...user,
      avatarText: (user.nickname || '我').slice(0, 1),
      roleText: displayRole,
    } : null;
    getApp().globalData.currentUser = user;
    this.setData({
      loading: false,
      user: profileUser,
      isManager: !!user && (user.role === 'manager' || user.role === 'super_admin' || isShopAdmin),
    });
  },
  openAuth() {
    wx.navigateTo({ url: '/pages/auth/index' });
  },
  openHistory() {
    wx.navigateTo({ url: '/pages/history/index' });
  },
  openProfileEdit() {
    wx.navigateTo({ url: '/pages/profile-edit/index' });
  },
  openManager() {
    wx.navigateTo({ url: '/pages/admin-menu/index' });
  },
  copySystemId() {
    if (!this.data.user || !this.data.user.systemId) return;
    wx.setClipboardData({
      data: this.data.user.systemId,
      success: () => wx.showToast({ title: '系统ID已复制', icon: 'success' }),
    });
  },
});
