const { loadMyOrders } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

const ORDER_STEPS = ['制作中', '已完成'];

Page({
  data: {
    activeOrders: [],
    completedOrders: [],
    cancelledOrders: [],
    loading: true,
  },

  async onShow() {
    this.syncTabBar();
    if (!(await requireLogin())) return;

    await this.loadOrders();
  },

  async onPullDownRefresh() {
    await this.loadOrders(true);
    wx.stopPullDownRefresh();
  },

  async loadOrders(force = false) {
    this.setData({ loading: true });
    let orders = [];

    try {
      orders = await loadMyOrders({ force });
    } catch (error) {
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }

    const withProgress = (order) => {
      const cancelled = order.status === '已取消';
      const steps = cancelled ? ['制作中', '已取消'] : ORDER_STEPS;
      const current = Math.max(0, steps.indexOf(order.status));
      return {
        ...order,
        isCancelled: cancelled,
        progress: steps.map((label, index) => ({
          label,
          completed: index < current,
          current: index === current,
          cancelled: cancelled && label === '已取消',
        })),
      };
    };

    const activeOrders = orders
      .filter((item) => item.status === '制作中')
      .map(withProgress);

    const completedOrders = orders
      .filter((item) => item.status === '已完成')
      .slice(0, 3)
      .map(withProgress);

    const cancelledOrders = orders
      .filter((item) => item.status === '已取消')
      .slice(0, 3)
      .map(withProgress);

    this.setData({
      loading: false,
      activeOrders,
      completedOrders,
      cancelledOrders,
    });
  },

  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 1 });
  },

  openOrder(event) {
    const id = event.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/history-detail/index?id=${id}` });
  },
});
