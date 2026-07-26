const { requireLogin } = require('../../utils/auth-guard');
const { changeCartQuantity, clearCart, getCartItems, submitCartOrder } = require('../../utils/cart-store');

Page({
  data: {
    items: [],
    total: '0.00',
    isSubmitting: false,
    remark: '',
  },
  async onShow() {
    if (!(await requireLogin())) return;
    this.renderCart();
  },
  increase(event) {
    this.changeQuantity(event.currentTarget.dataset.key, 1);
  },
  decrease(event) {
    this.changeQuantity(event.currentTarget.dataset.key, -1);
  },
  updateRemark(event) {
    this.setData({ remark: event.detail.value });
  },
  clearCart() {
    if (this.data.isSubmitting || !this.data.items.length) return;
    wx.showModal({
      title: '清空购物车',
      content: '确定移除当前已选的全部菜品吗？',
      confirmText: '清空',
      confirmColor: '#DC2626',
      success: (result) => {
        if (!result.confirm) return;
        clearCart();
        this.setData({ remark: '' });
        this.renderCart();
        wx.showToast({ title: '购物车已清空', icon: 'success' });
      },
    });
  },
  async submitOrder() {
    if (this.data.isSubmitting) return;
    if (!(await requireLogin())) return;
    this.setData({ isSubmitting: true });
    try {
      const result = await submitCartOrder(this.data.remark);
      if (!result.ok || !result.order) {
        if (['TABLE_REQUIRED', 'TABLE_NOT_AVAILABLE', 'INVALID_TABLE'].includes(result.code) || String(result.message || '').includes('桌码')) {
          wx.showModal({
            title: '请先扫码确认桌位',
            content: '请回到点餐页，点击右上角“扫码”确认桌码后再提交订单。',
            showCancel: false,
            success: () => wx.switchTab({ url: '/pages/menu/index' }),
          });
          return;
        }
        const dishNames = Array.isArray(result.dishNames) && result.dishNames.length
          ? result.dishNames.join('、')
          : '该菜品';
        const message = result.code === 'OUT_OF_STOCK'
          ? `${dishNames}库存不足，请调整数量后重试`
          : (result.message || '提交订单失败');
        throw new Error(message);
      }
      this.setData({ remark: '' });
      wx.showToast({ title: '订单已提交', icon: 'success' });
      setTimeout(() => wx.switchTab({ url: '/pages/orders/index' }), 500);
    } catch (error) {
      wx.showToast({ title: error.message || '提交失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
  changeQuantity(cartKey, delta) {
    if (!changeCartQuantity(cartKey, delta)) return;
    this.renderCart();
  },
  renderCart() {
    const items = getCartItems();
    const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
    this.setData({ items, total: total.toFixed(2) });
  },
});
