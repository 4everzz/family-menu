const { callAuth } = require('../../utils/auth-store');

Page({
  data: {
    isSubmitting: false,
  },
  async finishLogin(result) {
    getApp().globalData.currentUser = result.user;
    wx.showToast({ title: '登录成功', icon: 'success' });
    setTimeout(() => wx.navigateBack(), 400);
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
  async loginWithPhone(event) {
    const code = event.detail && event.detail.code;
    if (!code || this.data.isSubmitting) {
      if (!this.data.isSubmitting) wx.showToast({ title: '未完成手机号授权', icon: 'none' });
      return;
    }
    this.setData({ isSubmitting: true });
    try {
      const result = await callAuth('loginWithPhone', { code });
      if (!result.ok || !result.user) throw new Error(result.message || '手机号授权失败');
      await this.finishLogin(result);
    } catch (error) {
      wx.showToast({ title: error.message || '手机号授权失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
});
