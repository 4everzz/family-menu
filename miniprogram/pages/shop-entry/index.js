const { setCurrentShop } = require('../../utils/shop-store');

function readEntryCode(options) {
  const values = [
    options && options.code,
    options && options.shopCode,
    options && options.scene ? decodeURIComponent(options.scene) : '',
  ];
  for (const value of values) {
    const candidate = String(value || '').trim().toUpperCase();
    const directCode = candidate.replace(/^SHOP:/, '');
    if (/^[A-Z0-9]{8}$/.test(directCode)) return directCode;
    const match = candidate.match(/(?:^|[?&])(?:CODE|SHOPCODE)=([A-Z0-9]{8})(?:&|$)/);
    if (match) return match[1];
  }
  return '';
}

Page({
  data: {
    state: 'loading',
    message: '正在验证店铺入口',
  },
  onLoad(options) {
    const shopCode = readEntryCode(options);
    if (!shopCode) {
      this.setData({ state: 'error', message: '店铺入口无效，请重新扫描商家二维码' });
      return;
    }
    this.enterShop(shopCode);
  },
  async enterShop(shopCode) {
    try {
      const response = await wx.cloud.callFunction({
        name: 'shop-access',
        data: { action: 'joinWithShopCode', shopCode },
      });
      const result = response.result || {};
      if (!result.ok || !setCurrentShop(result.shop)) {
        throw new Error(result.message || '进入店铺失败');
      }
      this.setData({ state: 'success', message: `已进入${result.shop.name}` });
      setTimeout(() => wx.switchTab({ url: '/pages/menu/index' }), 500);
    } catch (error) {
      this.setData({ state: 'error', message: error.message || '进入店铺失败，请重新扫描二维码' });
    }
  },
  backToMenu() {
    wx.switchTab({ url: '/pages/menu/index' });
  },
});
