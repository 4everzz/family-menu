const { cacheCurrentUser, callAuth } = require('../../utils/auth-store');

Page({
  data: {
    isSubmitting: false,
  },
  onLoad(options) {
    const returnTo = String(options && options.returnTo || '');
    this.returnTo = returnTo.startsWith('/pages/') ? returnTo : '';
    this.allowIncompleteProfile = String(options && options.allowIncompleteProfile || '') === '1';
  },
  async finishLogin(result) {
    getApp().globalData.currentUser = result.user;
    cacheCurrentUser(result.user);
    wx.showToast({ title: '登录成功', icon: 'success' });
    setTimeout(() => {
      if (result.user.profileCompleted || this.allowIncompleteProfile) {
        if (this.returnTo) {
          wx.redirectTo({ url: this.returnTo });
          return;
        }
        wx.navigateBack();
        return;
      }
      const suffix = this.returnTo ? `?returnTo=${encodeURIComponent(this.returnTo)}` : '';
      wx.redirectTo({ url: `/pages/profile-edit/index${suffix}` });
    }, 400);
  },
  async loginWithWechat() {
    if (this.data.isSubmitting) return;
    this.setData({ isSubmitting: true });
    try {
      const result = await callAuth('loginWithWechat');
      if (!result.ok || !result.user) throw new Error(result.message || '微信登录失败');
      await this.finishLogin(result);
    } catch (error) {
      wx.showToast({ title: error.message || '微信登录失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
});
