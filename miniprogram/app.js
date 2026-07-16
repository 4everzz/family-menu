App({
  globalData: {
    cart: [],
    orders: [],
  },
  onLaunch() {
    if (wx.cloud) {
      wx.cloud.init({
        env: 'cloud1-d2gua37h7753f3812',
        traceUser: true,
      });
    }
    this.globalData.orders = wx.getStorageSync('family_orders') || [];
  },
  saveOrders() {
    wx.setStorageSync('family_orders', this.globalData.orders);
  },
});
