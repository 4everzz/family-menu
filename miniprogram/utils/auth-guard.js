const { refreshCurrentUser } = require('./auth-store');

async function requireLogin() {
  const user = await refreshCurrentUser();
  if (user) {
    getApp().globalData.currentUser = user;
    return user;
  }
  wx.showToast({ title: '请先登录', icon: 'none' });
  setTimeout(() => wx.navigateTo({ url: '/pages/auth/index' }), 200);
  return null;
}

module.exports = { requireLogin };
