const { callAdminMenu } = require('../../utils/shop-context');
const { invalidateMyOrders } = require('../../utils/order-store');

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
    isCancelling: previousOrders.some((previous) => previous.id === order.id && previous.isCancelling),
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
    cancelTarget: null,
    cancelReason: '',
    isCancelling: false,
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
      const historyOrders = allOrders.filter((item) => item.status !== '制作中').map((item) => normalizeAdminOrder(item));
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
      invalidateMyOrders();
      getApp().globalData.ordersUpdatedAt = Date.now();
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
  openCancelOrder(event) {
    const id = event.currentTarget.dataset.id;
    const targetOrder = this.data.orders.find((item) => item.id === id);
    if (!targetOrder || targetOrder.isCompleting || targetOrder.isCancelling) return;
    this.setData({ cancelTarget: targetOrder, cancelReason: '' });
  },
  closeCancelOrder() {
    if (!this.data.isCancelling) this.setData({ cancelTarget: null, cancelReason: '' });
  },
  inputCancelReason(event) {
    this.setData({ cancelReason: event.detail.value });
  },
  async submitCancelOrder() {
    const targetOrder = this.data.cancelTarget;
    const reason = String(this.data.cancelReason || '').trim();
    if (!targetOrder || this.data.isCancelling) return;
    if (reason.length < 2) {
      wx.showToast({ title: '请填写至少 2 个字的取消原因', icon: 'none' });
      return;
    }
    this.setData({
      isCancelling: true,
      orders: this.data.orders.map((item) => ({ ...item, isCancelling: item.id === targetOrder.id ? true : item.isCancelling })),
    });
    try {
      const result = await this.callAdmin('cancelOrder', { id: targetOrder.id, reason });
      if (!result.ok) {
        wx.showToast({ title: result.message || '订单状态已变化，请刷新后重试', icon: 'none' });
        return;
      }
      invalidateMyOrders();
      getApp().globalData.ordersUpdatedAt = Date.now();
      wx.showToast({ title: '订单已取消', icon: 'success' });
      this.setData({ cancelTarget: null, cancelReason: '' });
      await this.loadOrders();
    } catch (error) {
      wx.showToast({ title: '取消订单失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isCancelling: false });
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
