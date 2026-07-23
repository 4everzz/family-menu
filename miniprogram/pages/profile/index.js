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
    migrationCompleted: true,
    migrationLoading: false,
    migrationConfirming: false,
    migrationButtonText: '初始化多商家数据',
    migrationError: '',
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
    if (user && user.role === 'super_admin') await this.loadMigrationStatus();
  },
  async loadMigrationStatus() {
    try {
      const response = await wx.cloud.callFunction({
        name: 'shop-access',
        data: { action: 'getMigrationStatus' },
      });
      const result = response.result || {};
      this.setData({ migrationCompleted: result.ok && result.migrated === true });
    } catch (error) {
      this.setData({ migrationCompleted: true });
    }
  },
  onHide() {
    this.clearMigrationConfirm();
  },
  clearMigrationConfirm() {
    if (this.migrationConfirmTimer) clearTimeout(this.migrationConfirmTimer);
    this.migrationConfirmTimer = null;
    if (this.data.migrationConfirming) {
      this.setData({ migrationConfirming: false, migrationButtonText: '初始化多商家数据' });
    }
  },
  initializeMultiShop() {
    if (this.data.migrationLoading) return;
    if (!this.data.migrationConfirming) {
      this.setData({ migrationConfirming: true, migrationButtonText: '再次点击确认初始化' });
      this.migrationConfirmTimer = setTimeout(() => this.clearMigrationConfirm(), 8000);
      return;
    }
    this.clearMigrationConfirm();
    this.setData({ migrationLoading: true, migrationButtonText: '正在初始化多商家数据', migrationError: '' });
    wx.cloud.callFunction({
      name: 'shop-access',
      data: { action: 'migrateDefaultShop' },
    }).then((response) => {
      const result = response.result || {};
      if (!result.ok) {
        const error = new Error(result.message || '初始化失败');
        error.debugMessage = result.debugMessage || '';
        throw error;
      }
      this.setData({ migrationCompleted: true });
      const code = result.initialCodes && result.initialCodes.shopCode;
      if (code) {
        wx.setClipboardData({ data: code, success: () => wx.showToast({ title: '店铺码已复制', icon: 'success' }) });
      } else {
        wx.showToast({ title: '初始化完成', icon: 'success' });
      }
      this.setData({ migrationLoading: false, migrationButtonText: '初始化多商家数据' });
    }).catch((error) => {
      wx.showToast({ title: error.message || '初始化失败，请重试', icon: 'none' });
      this.setData({
        migrationLoading: false,
        migrationButtonText: '初始化多商家数据',
        migrationError: error.debugMessage || '云函数调用失败，请检查部署状态',
      });
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
  openShopManager() {
    wx.navigateTo({ url: '/pages/admin-shops/index' });
  },
  openUserManager() {
    wx.navigateTo({ url: '/pages/admin-users/index' });
  },
});
