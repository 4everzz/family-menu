const { loadMyOrders } = require('../../utils/order-store');
const { refreshCurrentUser } = require('../../utils/auth-store');

Page({
  data: { historyOrders: [], loading: true },
  async onShow() {
    if (!(await refreshCurrentUser())) {
      wx.showToast({ title: '请先登录后查看历史订单', icon: 'none' });
      wx.switchTab({ url: '/pages/profile/index' });
      return;
    }

    await this.loadHistory();
  },

  async onPullDownRefresh() {
    await this.loadHistory(true);
    wx.stopPullDownRefresh();
  },

  async loadHistory(force = false) {
    this.setData({ loading: true });
    let orders = [];
    try {
      orders = await loadMyOrders({ force });
    } catch (error) {
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
    const historyOrders = orders
      .filter((order) => order.status === '已完成' || order.status === '已取消')
      .map((order) => ({
        id: order.id,
        status: order.status,
        summary: order.summary,
        createdAt: order.createdAt,
        total: order.total,
        statusNote: order.statusNote || '',
      }));
    this.setData({ historyOrders, loading: false });
  },
  openOrder(event) {
    wx.navigateTo({ url: `/pages/history-detail/index?id=${event.currentTarget.dataset.id}` });
  },
});
