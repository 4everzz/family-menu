export function parseEntryCode(value) {
  const candidate = String(value || '').trim().toUpperCase();
  const directCode = candidate.replace(/^(TABLE|SHOP):/, '');
  if (/^[A-Z0-9]{8}$/.test(directCode)) return directCode;

  const match = candidate.match(/(?:^|[?&])(TABLECODE|SHOPCODE|CODE)=([A-Z0-9]{8})(?:&|$)/);
  if (match) return match[2];

  const sceneMatch = candidate.match(/(?:^|[?&])SCENE=(?:TABLE%3A|SHOP%3A)?([A-Z0-9]{8})(?:&|$)/);
  return sceneMatch ? sceneMatch[1] : '';
}

export function getGuestSessionId() {
  const key = 'uni_family_guest_session_id';
  const cached = String(uni.getStorageSync(key) || '').trim();
  if (/^guest_[A-Za-z0-9_-]{12,64}$/.test(cached)) return cached;

  const id = `guest_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
  uni.setStorageSync(key, id);
  return id;
}
