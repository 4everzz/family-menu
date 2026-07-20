const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');

Page({
  data: {
    loading: true,
    nickname: '',
    avatarFileId: '',
    avatarUrl: '',
    avatarText: '我',
    imageUploading: false,
    saving: false,
  },
  async onShow() {
    const user = await refreshCurrentUser();
    if (!user) {
      wx.redirectTo({ url: '/pages/auth/index' });
      return;
    }
    this.setData({
      loading: false,
      nickname: user.profileCompleted ? user.nickname : '',
      avatarFileId: user.avatarFileId || '',
      avatarUrl: user.avatarUrl || '',
      avatarText: (user.nickname || '我').slice(0, 1),
    });
  },
  updateNickname(event) {
    const nickname = event.detail.value;
    this.setData({ nickname, avatarText: (nickname.trim() || '我').slice(0, 1) });
  },
  async chooseAvatar(event) {
    const filePath = event.detail && event.detail.avatarUrl;
    if (!filePath || this.data.imageUploading) return;
    const extension = (filePath.match(/\.([a-zA-Z0-9]+)$/) || [])[1] || 'jpg';
    this.setData({ imageUploading: true });
    try {
      const result = await wx.cloud.uploadFile({
        cloudPath: `avatars/${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${extension.toLowerCase()}`,
        filePath,
      });
      if (!result.fileID) throw new Error('头像上传失败');
      this.setData({ avatarFileId: result.fileID, avatarUrl: filePath });
    } catch (error) {
      wx.showToast({ title: error.message || '头像上传失败', icon: 'none' });
    } finally {
      this.setData({ imageUploading: false });
    }
  },
  async saveProfile() {
    const nickname = this.data.nickname.trim();
    if (!nickname) {
      wx.showToast({ title: '请填写昵称', icon: 'none' });
      return;
    }
    this.setData({ saving: true });
    try {
      const result = await callAuth('updateProfile', { nickname, avatarFileId: this.data.avatarFileId });
      if (!result.ok || !result.user) throw new Error(result.message || '保存失败');
      getApp().globalData.currentUser = result.user;
      wx.showToast({ title: '资料已保存', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 350);
    } catch (error) {
      wx.showToast({ title: error.message || '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },
});
