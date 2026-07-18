const { loadMyOrders } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

Page({
  data: { historyOrders: [], loading: true },
  async onShow() {
    if (!(await requireLogin())) return;
    this.setData({ loading: true });
    let orders = [];
    try {
      orders = await loadMyOrders();
    } catch (error) {
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
    const historyOrders = orders
      .filter((order) => order.status === '已完成')
      .map((order) => ({
        id: order.id,
        status: order.status,
        summary: order.summary,
        createdAt: order.createdAt,
        total: order.total,
      }));
    this.setData({ historyOrders, loading: false });
  },
  openOrder(event) {
    wx.navigateTo({ url: `/pages/history-detail/index?id=${event.currentTarget.dataset.id}` });
  },
});
