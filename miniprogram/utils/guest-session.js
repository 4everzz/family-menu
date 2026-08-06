const GUEST_SESSION_KEY = 'guest-session-id';

function createGuestSessionId() {
  return `guest_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
}

function getGuestSessionId() {
  const cached = String(wx.getStorageSync(GUEST_SESSION_KEY) || '').trim();
  if (/^guest_[A-Za-z0-9_-]{12,64}$/.test(cached)) return cached;
  const guestSessionId = createGuestSessionId();
  wx.setStorageSync(GUEST_SESSION_KEY, guestSessionId);
  return guestSessionId;
}

module.exports = { getGuestSessionId };
