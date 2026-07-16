App({
  globalData: {
    cart: [],
    orders: [],
  },
  onLaunch() {
    this.globalData.orders = wx.getStorageSync('family_orders') || [];
  },
  saveOrders() {
    wx.setStorageSync('family_orders', this.globalData.orders);
  },
});
