App({
  globalData: {
    cart: [],
    orders: [],
    menuUpdatedAt: 0,
    currentShop: null,
  },
  onLaunch() {
    if (wx.cloud) {
      wx.cloud.init({
        env: 'cloud1-d2gua37h7753f3812',
        traceUser: true,
      });
    }
    this.globalData.orders = wx.getStorageSync('family_orders') || [];
    this.globalData.currentShop = null;
    this.globalData.cart = [];
    wx.removeStorageSync('family_cart');
    wx.removeStorageSync('current_shop_context');
  },
  saveCart() {
    wx.setStorageSync('family_cart', this.globalData.cart);
  },
  saveOrders() {
    wx.setStorageSync('family_orders', this.globalData.orders);
  },
});
