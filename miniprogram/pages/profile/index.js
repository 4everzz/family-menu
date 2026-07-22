const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');

function getRoleText(role) {
  if (role === 'super_admin') return '超级管理员';
  if (role === 'manager') return '管理员';
  return '普通用户';
}

Page({
  data: {
    loading: true,
    user: null,
    isManager: false,
    isSuperAdmin: false,
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
    const profileUser = user ? {
      ...user,
      avatarText: (user.nickname || '我').slice(0, 1),
      roleText: getRoleText(user.role),
    } : null;
    getApp().globalData.currentUser = user;
    this.setData({
      loading: false,
      user: profileUser,
      isManager: !!user && (user.role === 'manager' || user.role === 'super_admin'),
      isSuperAdmin: !!user && user.role === 'super_admin',
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
  openUserManager() {
    wx.navigateTo({ url: '/pages/admin-users/index' });
  },
});
