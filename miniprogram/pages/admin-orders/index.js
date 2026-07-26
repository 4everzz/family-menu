const { callAdminMenu } = require('../../utils/shop-context');

function getDishOptionsText(dish) {
  return dish.optionsText || (Array.isArray(dish.options) ? dish.options.join('、') : '');
}

function getDishSummary(dish) {
  const optionsText = getDishOptionsText(dish);
  return `${dish.name} × ${dish.quantity}${optionsText ? `（${optionsText}）` : ''}`;
}

function normalizeAdminOrder(order, previousOrders = []) {
  const items = (order.items || []).map((dish) => ({
    ...dish,
    optionsText: getDishOptionsText(dish),
  }));
  return {
    ...order,
    items,
    summary: order.summaryWithOptions || items.map(getDishSummary).join('、') || order.summary || '',
    isCompleting: previousOrders.some((previous) => previous.id === order.id && previous.isCompleting),
  };
}

Page({
  data: {
    loading: true,
    hasAccess: false,
    orders: [],
    historyOrders: [],
    activeTab: 'active',
    selectedOrder: null,
  },
  onShow() {
    this.loadOrders();
  },
  async callAdmin(action, payload = {}) {
    return callAdminMenu(action, payload);
  },
  async loadOrders() {
    this.setData({ loading: true });
    try {
      const result = await this.callAdmin('listAdminOrders');
      if (!result.ok) {
        this.setData({ hasAccess: false, orders: [], loading: false });
        return;
      }
      const allOrders = result.orders || [];
      const previousOrders = this.data.orders;
      const orders = allOrders.filter((item) => item.status === '制作中').map((item) => normalizeAdminOrder(item, previousOrders));
      const historyOrders = allOrders.filter((item) => item.status === '已完成').map((item) => normalizeAdminOrder(item));
      this.setData({ hasAccess: true, orders, historyOrders, loading: false });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: '读取订单失败，请稍后重试', icon: 'none' });
    }
  },
  async completeOrder(event) {
    const id = event.currentTarget.dataset.id;
    const targetOrder = this.data.orders.find((item) => item.id === id);
    if (!targetOrder || targetOrder.isCompleting) return;
    this.setData({
      orders: this.data.orders.map((item) => ({
        ...item,
        isCompleting: item.id === id ? true : item.isCompleting,
      })),
    });
    try {
      const result = await this.callAdmin('completeOrder', { id });
      if (!result.ok) {
        wx.showToast({ title: result.message || '订单状态已变化，请刷新后重试', icon: 'none' });
        return;
      }
      wx.showToast({ title: '订单已完成', icon: 'success' });
      await this.loadOrders();
    } catch (error) {
      wx.showToast({ title: '更新订单失败，请稍后重试', icon: 'none' });
    } finally {
      const stillVisible = this.data.orders.some((item) => item.id === id);
      if (stillVisible) {
        this.setData({
          orders: this.data.orders.map((item) => ({
            ...item,
            isCompleting: item.id === id ? false : item.isCompleting,
          })),
        });
      }
    }
  },
  switchTab(event) {
    this.setData({ activeTab: event.currentTarget.dataset.tab });
  },
  openOrder(event) {
    const id = event.currentTarget.dataset.id;
    const order = [...this.data.orders, ...this.data.historyOrders].find((item) => item.id === id);
    if (order) this.setData({ selectedOrder: order });
  },
  closeHistoryOrder() {
    this.setData({ selectedOrder: null });
  },
  stopModalPropagation() {
  },
});
