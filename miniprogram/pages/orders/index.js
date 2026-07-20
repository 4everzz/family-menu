const { loadMyOrders } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

Page({
  data: { activeOrders: [], completedOrders: [], loading: true },
  async onShow() {
    this.syncTabBar();
    if (!(await requireLogin())) return;
    this.setData({ loading: true });
    let orders = [];
    try {
      orders = await loadMyOrders();
    } catch (error) {
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
    const steps = ['制作中', '已完成'];
    const withProgress = (order) => {
      const current = Math.max(0, steps.indexOf(order.status));
      return {
        ...order,
        progress: steps.map((label, index) => ({ label, active: index <= current })),
      };
    };
    const activeOrders = orders.filter((item) => item.status === '制作中').map(withProgress);
    const completedOrders = orders.filter((item) => item.status === '已完成').slice(0, 3).map(withProgress);
    this.setData({
      loading: false,
      activeOrders,
      completedOrders,
    });
  },
  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 1 });
  },
});
