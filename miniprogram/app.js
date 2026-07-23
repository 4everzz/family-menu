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
    const savedCart = wx.getStorageSync('family_cart');
    this.globalData.cart = Array.isArray(savedCart) ? savedCart : [];
    this.globalData.orders = wx.getStorageSync('family_orders') || [];
    this.globalData.currentShop = wx.getStorageSync('current_shop_context') || null;
  },
  saveCart() {
    wx.setStorageSync('family_cart', this.globalData.cart);
  },
  saveOrders() {
    wx.setStorageSync('family_orders', this.globalData.orders);
  },
});
