const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');
const { getCurrentShopSnapshot } = require('../../utils/shop-context');

function getShopRoleText(role) {
  if (role === 'store_owner') return '一级管理员';
  if (role === 'store_staff') return '二级管理员';
  if (role === 'store_admin') return '店铺管理员';
  return '';
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
    let shopRole = '';
    let isShopAdmin = false;
    if (user) {
      try {
        const result = await getCurrentShopSnapshot();
        if (result.ok && result.access) {
          shopRole = result.access.role === 'super_admin'
            ? '超级管理员'
            : getShopRoleText(result.access.role);
          isShopAdmin = result.access.isManager === true;
        }
      } catch (e) {
        // 当前未进入店铺或网络暂时不可用时保持普通用户展示。
      }
    }
    const displayRole = shopRole || (user && user.role === 'super_admin' ? '超级管理员' : '普通用户');
    const profileUser = user ? {
      ...user,
      avatarText: (user.nickname || '我').slice(0, 1),
      roleText: displayRole,
    } : null;
    getApp().globalData.currentUser = user;
    this.setData({
      loading: false,
      user: profileUser,
      isManager: !!user && isShopAdmin,
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
