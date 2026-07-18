const { loadMyOrders } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

Page({
  data: { currentOrder: null, loading: true },
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
    const order = orders.find((item) => item.status !== '已完成');
    if (!order) {
      this.setData({ currentOrder: null, loading: false });
      return;
    }
    const steps = ['制作中', '已完成'];
    const current = Math.max(0, steps.indexOf(order.status));
    this.setData({
      loading: false,
      currentOrder: {
        ...order,
        progress: steps.map((label, index) => ({ label, active: index <= current })),
      },
    });
  },
  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 1 });
  },
});
