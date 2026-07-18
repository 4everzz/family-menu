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
  openManager() {
    wx.navigateTo({ url: '/pages/admin-menu/index' });
  },
  openUserManager() {
    wx.navigateTo({ url: '/pages/admin-users/index' });
  },
  async bindPhone(event) {
    const code = event.detail && event.detail.code;
    if (!code) {
      wx.showToast({ title: '未完成手机号授权', icon: 'none' });
      return;
    }
    try {
      const result = await callAuth('loginWithPhone', { code });
      if (!result.ok || !result.user) throw new Error(result.message || '手机号授权失败');
      getApp().globalData.currentUser = result.user;
      wx.showToast({ title: '手机号已授权', icon: 'success' });
      this.loadCurrentUser();
    } catch (error) {
      wx.showToast({ title: error.message || '手机号授权失败', icon: 'none' });
    }
  },
});
