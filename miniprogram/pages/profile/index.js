const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');

function getRoleText(role) {
  if (role === 'super_admin') return '超级管理员';
  if (role === 'manager') return '管理员';
  return '普通用户';
}

function isShopManagerRole(role) {
  return ['store_admin', 'store_owner', 'store_staff'].includes(role);
}

function getShopRoleText(role) {
  if (role === 'store_admin' || role === 'store_owner') return '一级管理员';
  if (role === 'store_staff') return '二级管理员';
  if (role === 'super_admin') return '超级管理员';
  return '顾客';
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
    myShops: [],
    loadingShops: false,
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
    this.loadMyShops();
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
  async loadMyShops() {
    if (this.data.loadingShops) return;
    this.setData({ loadingShops: true });
    try {
      var result = await wx.cloud.callFunction({ name: 'shop-access', data: { action: 'listMyShops' } });
      if (result.result && result.result.ok) {
        const shops = (result.result.shops || []).map((shop) => ({
          ...shop,
          roleText: getShopRoleText(shop.role),
        }));
        const hasShopManagerRole = shops.some((shop) => isShopManagerRole(shop.role));
        this.setData({ myShops: shops, isManager: this.data.isManager || hasShopManagerRole });
      }
    } catch (e) {}
    this.setData({ loadingShops: false });
  },
  rejoinShop(event) {
    var shopId = event.currentTarget.dataset.id;
    var shop = this.data.myShops.find((item) => item.id === shopId);
    if (!shop) return;
    wx.showLoading({ title: '进入店铺' });
    wx.cloud.callFunction({ name: 'shop-access', data: { action: 'rejoinShop', shopId: shop.id } }).then(function(r) {
      var result = r.result || {};
      if (!result.ok || !result.shop) throw new Error(result.message || '进入店铺失败');
      var ss = require('../../utils/shop-store');
      if (!ss.setCurrentShop(result.shop)) throw new Error('设置店铺失败');
      wx.hideLoading();
      wx.switchTab({ url: '/pages/menu/index' });
    }).catch(function(e) {
      wx.hideLoading();
      wx.showToast({ title: e.message || '进入店铺失败', icon: 'none' });
    });
  },
  openShopManager() {
    wx.navigateTo({ url: '/pages/admin-shops/index' });
  },
  openUserManager() {
    wx.navigateTo({ url: '/pages/admin-users/index' });
  },
  copySystemId() {
    if (!this.data.user || !this.data.user.systemId) return;
    wx.setClipboardData({
      data: this.data.user.systemId,
      success: () => wx.showToast({ title: '系统ID已复制', icon: 'success' }),
    });
  },
});
