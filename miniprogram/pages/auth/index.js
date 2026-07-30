const { cacheCurrentUser, callAuth } = require('../../utils/auth-store');

Page({
  data: {
    isSubmitting: false,
  },
  async finishLogin(result) {
    getApp().globalData.currentUser = result.user;
    cacheCurrentUser(result.user);
    wx.showToast({ title: '登录成功', icon: 'success' });
    setTimeout(() => {
      if (result.user.profileCompleted) {
        wx.navigateBack();
        return;
      }
      wx.redirectTo({ url: '/pages/profile-edit/index' });
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
