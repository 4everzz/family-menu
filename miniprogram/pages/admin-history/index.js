const { loadAdminOrders } = require('../../utils/admin-order-store');

Page({
  data: { loading: true, hasAccess: false, orders: [] },
  onShow() {
    this.loadOrders();
  },
  async loadOrders() {
    this.setData({ loading: true });
    try {
      const orders = await loadAdminOrders();
      this.setData({
        hasAccess: true,
        loading: false,
        orders: orders.filter((item) => item.status === '已完成').map((item) => ({
          id: item.id,
          createdAt: item.createdAt,
          summary: item.summary || (item.items || []).map((dish) => `${dish.name} × ${dish.quantity}`).join('、'),
          total: item.total,
        })),
      });
    } catch (error) {
      this.setData({ hasAccess: false, orders: [], loading: false });
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
  },
  openOrder(event) {
    wx.navigateTo({ url: `/pages/admin-order-detail/index?id=${event.currentTarget.dataset.id}` });
  },
});
