Page({
  data: { currentOrder: null, isCompleting: false },
  onShow() {
    this.syncTabBar();
    const steps = ['制作中', '已完成'];
    const legacyStatuses = ['已提交', '待接单', '待上菜', '待取餐'];
    const order = getApp().globalData.orders.find((item) => item.status !== '已完成');
    if (!order) {
      this.setData({ currentOrder: null, isCompleting: false });
      return;
    }
    const isLegacyStatus = legacyStatuses.includes(order.status);
    const status = isLegacyStatus ? '制作中' : order.status;
    const current = Math.max(0, steps.indexOf(status));
    this.setData({
      currentOrder: {
        ...order,
        status,
        statusNote: isLegacyStatus ? '订单已提交，正在制作中' : order.statusNote,
        progress: steps.map((label, index) => ({ label, active: index <= current })),
      },
    });
  },
  syncTabBar() {
    const tabBar = this.getTabBar && this.getTabBar();
    if (tabBar) tabBar.setData({ selected: 1 });
  },
  completeOrder() {
    const currentOrder = this.data.currentOrder;
    if (!currentOrder || this.data.isCompleting) return;
    this.setData({ isCompleting: true });
    wx.showModal({
      title: '确认完成订单',
      content: '确认这笔订单已经完成用餐吗？',
      success: (result) => {
        if (!result.confirm) {
          this.setData({ isCompleting: false });
          return;
        }
        const app = getApp();
        const order = app.globalData.orders.find((item) => item.id === currentOrder.id);
        if (!order || order.status === '已完成') {
          this.setData({ isCompleting: false });
          this.onShow();
          return;
        }
        order.status = '已完成';
        order.statusNote = '订单已完成，感谢使用小家菜单';
        app.saveOrders();
        wx.showToast({ title: '订单已完成', icon: 'success' });
        this.setData({ isCompleting: false });
        this.onShow();
      },
    });
  },
});
