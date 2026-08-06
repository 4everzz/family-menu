const { refreshCurrentUser } = require('./auth-store');

async function requireLogin(options = {}) {
  const returnTo = String(options.returnTo || '').startsWith('/pages/') ? String(options.returnTo) : '';
  const allowIncompleteProfile = options.allowIncompleteProfile === true;
  const user = await refreshCurrentUser();
  if (user) {
    getApp().globalData.currentUser = user;
    if (!allowIncompleteProfile && !user.profileCompleted) {
      wx.showToast({ title: '请先完善资料', icon: 'none' });
      const suffix = returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : '';
      setTimeout(() => wx.navigateTo({ url: `/pages/profile-edit/index${suffix}` }), 200);
      return null;
    }
    return user;
  }
  wx.showToast({ title: '请先登录', icon: 'none' });
  const query = [];
  if (returnTo) query.push(`returnTo=${encodeURIComponent(returnTo)}`);
  if (allowIncompleteProfile) query.push('allowIncompleteProfile=1');
  const suffix = query.length ? `?${query.join('&')}` : '';
  setTimeout(() => wx.navigateTo({ url: `/pages/auth/index${suffix}` }), 200);
  return null;
}

module.exports = { requireLogin };
