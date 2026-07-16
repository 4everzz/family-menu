Page({
  data: { orders: [] },
  onShow() {
    const steps = ['制作中', '已完成'];
    const legacyStatuses = ['已提交', '待接单', '待上菜', '待取餐'];
    const orders = getApp().globalData.orders.map((order) => {
      const isLegacyStatus = legacyStatuses.includes(order.status);
      const status = isLegacyStatus ? '制作中' : order.status;
      const current = Math.max(0, steps.indexOf(status));
      return {
        ...order,
        status,
        statusNote: isLegacyStatus ? '订单已提交，正在制作中' : order.statusNote,
        progress: steps.map((label, index) => ({ label, active: index <= current })),
      };
    });
    this.setData({ orders });
  },
});
