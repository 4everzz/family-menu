const { loadAdminOrder } = require('../../utils/admin-order-store');

Page({
  data: { loading: true, hasAccess: false, order: null },
  async onLoad(query) {
    const id = String(query.id || '');
    if (!id) {
      wx.showToast({ title: '订单不存在', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 400);
      return;
    }
    try {
      const order = await loadAdminOrder(id);
      if (!order) {
        wx.showToast({ title: '订单不存在', icon: 'none' });
        setTimeout(() => wx.navigateBack(), 400);
        return;
      }
      this.setData({ hasAccess: true, order, loading: false });
    } catch (error) {
      this.setData({ hasAccess: false, loading: false });
      wx.showToast({ title: error.message || '读取订单失败', icon: 'none' });
    }
  },
});
