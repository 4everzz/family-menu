const { refreshCurrentUser } = require('./auth-store');

async function requireLogin() {
  const user = await refreshCurrentUser();
  if (user) {
    getApp().globalData.currentUser = user;
    if (!user.profileCompleted) {
      wx.showToast({ title: '请先完善资料', icon: 'none' });
      setTimeout(() => wx.navigateTo({ url: '/pages/profile-edit/index' }), 200);
      return null;
    }
    return user;
  }
  wx.showToast({ title: '请先登录', icon: 'none' });
  setTimeout(() => wx.navigateTo({ url: '/pages/auth/index' }), 200);
  return null;
}

module.exports = { requireLogin };
