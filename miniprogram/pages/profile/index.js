Page({
  data: {
    isLoggedIn: false,
  },
  onShow() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 2 });
  },
  showLoginNotice() {
    wx.showToast({ title: '登录功能将在云开发阶段接入', icon: 'none' });
  },
  openHistory() {
    wx.navigateTo({ url: '/pages/history/index' });
  },
  showManagerNotice() {
    wx.navigateTo({ url: '/pages/admin-menu/index' });
  },
});
