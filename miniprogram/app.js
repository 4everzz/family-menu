App({
  globalData: {
    cart: [],
    orders: [],
    menuUpdatedAt: 0,
    ordersUpdatedAt: 0,
    membersUpdatedAt: 0,
    currentShop: null,
    orderRequestId: '',
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
    // 购物车变化后必须生成新的下单请求，避免旧请求复用到新购物车。
    this.globalData.orderRequestId = '';
    wx.setStorageSync('family_cart', this.globalData.cart);
  },
  saveOrders() {
    wx.setStorageSync('family_orders', this.globalData.orders);
  },
});
