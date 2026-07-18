async function callAuth(action, payload = {}) {
  const response = await wx.cloud.callFunction({
    name: 'auth',
    data: { action, ...payload },
  });
  return response.result || {};
}

async function refreshCurrentUser() {
  try {
    const result = await callAuth('getCurrentUser');
    return result.ok && result.user ? result.user : null;
  } catch (error) {
    return null;
  }
}

module.exports = {
  callAuth,
  refreshCurrentUser,
};
