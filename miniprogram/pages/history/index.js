Page({
  data: { historyOrders: [] },
  onShow() {
    const orders = getApp().globalData.orders;
    const currentOrder = orders.find((item) => item.status !== '已完成');
    const historyOrders = orders
      .filter((item) => item !== currentOrder)
      .map((order) => ({
        id: order.id,
        status: order.status,
        summary: order.summary || (order.items || []).map((item) => `${item.name} × ${item.quantity}`).join('、'),
        createdAt: order.createdAt,
        total: order.total,
      }));
    this.setData({ historyOrders });
  },
  openOrder(event) {
    wx.navigateTo({ url: `/pages/history-detail/index?id=${event.currentTarget.dataset.id}` });
  },
});
