const { loadMyOrders } = require('../../utils/order-store');
const { requireLogin } = require('../../utils/auth-guard');

const ORDER_STEPS = ['制作中', '已完成'];

Page({
  data: {
    activeOrders: [],
    completedOrders: [],
    loading: true,
  },

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

    const withProgress = (order) => {
      const current = Math.max(0, ORDER_STEPS.indexOf(order.status));
      return {
        ...order,
        progress: ORDER_STEPS.map((label, index) => ({
          label,
          completed: index < current,
          current: index === current,
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

  openOrder(event) {
    const id = event.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: `/pages/history-detail/index?id=${id}` });
  },
});
