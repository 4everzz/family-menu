Page({
  data: { orders: [] },
  onShow() {
    const steps = ['已提交', '制作中', '待上菜', '已完成'];
    const orders = getApp().globalData.orders.map((order) => {
      const current = Math.max(0, steps.indexOf(order.status));
      return {
        ...order,
        progress: steps.map((label, index) => ({ label, active: index <= current })),
      };
    });
    this.setData({ orders });
  },
});
