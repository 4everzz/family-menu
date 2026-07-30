const { callAdminMenu, ensureCurrentShop } = require('../../utils/shop-context');

Page({
  data: {
    loading: true,
    hasAccess: false,
    shopName: '',
    days: 7,
    rangeText: '',
    summary: [],
    daily: [],
    topDishes: [],
    lastOrdersUpdatedAt: 0,
  },
  onLoad() {
    this.setData({ lastOrdersUpdatedAt: getApp().globalData.ordersUpdatedAt || 0 });
    this.loadStats();
  },
  onShow() {
    const updatedAt = getApp().globalData.ordersUpdatedAt || 0;
    if (updatedAt && updatedAt !== this.data.lastOrdersUpdatedAt) {
      this.setData({ lastOrdersUpdatedAt: updatedAt });
      this.loadStats();
    }
  },
  async loadStats() {
    this.setData({ loading: true });
    try {
      const shop = await ensureCurrentShop();
      const result = await callAdminMenu('getShopStats', { days: this.data.days });
      if (!result.ok || !result.stats) {
        this.setData({ loading: false, hasAccess: false });
        return;
      }
      const stats = result.stats;
      const maxRevenue = stats.daily.reduce((max, day) => Math.max(max, day.revenue), 0);
      const daily = stats.daily.map((day) => ({
        ...day,
        revenueText: day.revenue.toFixed(2),
        percent: maxRevenue > 0
          ? Math.max(Math.round((day.revenue / maxRevenue) * 100), day.revenue > 0 ? 4 : 0)
          : 0,
      }));
      const topDishes = stats.topDishes.map((dish) => ({
        ...dish,
        revenueText: dish.revenue.toFixed(2),
      }));
      this.setData({
        loading: false,
        hasAccess: true,
        shopName: shop.name || '当前店铺',
        rangeText: `${stats.startKey} ~ ${stats.endKey}`,
        daily,
        topDishes,
        summary: [
          { label: '订单数', value: String(stats.orderCount) },
          { label: '营业额', value: `¥${stats.revenue.toFixed(2)}` },
          { label: '完成客单', value: `¥${stats.averageOrder.toFixed(2)}` },
          { label: '完成率', value: `${stats.completionRate}%` },
          { label: '已完成订单', value: String(stats.completedCount) },
          { label: '完成订单中桌码占比', value: `${stats.tableOrderRate}%` },
        ],
      });
    } catch (error) {
      this.setData({ loading: false, hasAccess: false });
      wx.showToast({ title: '读取报表失败', icon: 'none' });
    }
  },
  switchRange(event) {
    const days = Number(event.currentTarget.dataset.days);
    if (!days || days === this.data.days) return;
    this.setData({ days });
    this.loadStats();
  },
});
