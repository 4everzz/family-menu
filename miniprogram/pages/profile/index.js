Page({
  data: {
    isLoggedIn: false,
  },
  showLoginNotice() {
    wx.showToast({ title: '登录功能将在云开发阶段接入', icon: 'none' });
  },
  showManagerNotice() {
    wx.showToast({ title: '管理端将在后续阶段实现', icon: 'none' });
  },
});
