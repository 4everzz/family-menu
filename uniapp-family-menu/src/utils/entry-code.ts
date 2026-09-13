/**
 * 从二维码、链接参数或小程序场景值中解析 8 位入口码。
 * 兼容三种写法：裸码、TABLE:/SHOP: 前缀、以及带 query 的完整链接。
 */
export function parseEntryCode(value: unknown): string {
  const candidate = String(value || '').trim().toUpperCase();
  const directCode = candidate.replace(/^(TABLE|SHOP):/, '');
  if (/^[A-Z0-9]{8}$/.test(directCode)) return directCode;

  const match = candidate.match(/(?:^|[?&])(TABLECODE|SHOPCODE|CODE)=([A-Z0-9]{8})(?:&|$)/);
  if (match) return match[2];

  const sceneMatch = candidate.match(/(?:^|[?&])SCENE=(?:TABLE%3A|SHOP%3A)?([A-Z0-9]{8})(?:&|$)/);
  return sceneMatch ? sceneMatch[1] : '';
}

/**
 * 获取访客会话 ID：未登录用户也用同一个 ID 归属购物车，
 * 保证游客态加购不丢；已有合法 ID 直接复用，否则生成并落盘。
 */
export function getGuestSessionId(): string {
  const key = 'uni_family_guest_session_id';
  const cached = String(uni.getStorageSync(key) || '').trim();
  if (/^guest_[A-Za-z0-9_-]{12,64}$/.test(cached)) return cached;

  const id = `guest_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
  uni.setStorageSync(key, id);
  return id;
}
