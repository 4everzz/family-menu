const { callAdminMenu, ensureCurrentShop } = require('../../utils/shop-context');

Page({
  data: {
    loading: true,
    hasAccess: false,
    navigatingTarget: '',
    shopName: '',
    stats: [
      { label: '制作中订单', value: '—' },
      { label: '可点菜品', value: '—' },
      { label: '菜品分类', value: '—' },
    ],
  },
  onShow() {
    this.setData({ navigatingTarget: '' });
    this.loadAccess();
  },
  async callAdmin(action, payload = {}) {
    return callAdminMenu(action, payload);
  },
  async loadAccess() {
    this.setData({ loading: true });
    try {
      const shop = await ensureCurrentShop();
      const [categoryResult, dishResult, orderResult] = await Promise.all([
        this.callAdmin('listCategories'),
        this.callAdmin('listDishes'),
        this.callAdmin('listAdminOrders'),
      ]);
      if (categoryResult.ok && dishResult.ok && orderResult.ok) {
        const makingOrders = (orderResult.orders || []).filter((item) => item.status === '制作中').length;
        const availableDishes = (dishResult.dishes || []).filter((item) => {
          const stock = Number(item.stock);
          return item.enabled !== false && item.manualSoldOut !== true && (!Number.isFinite(stock) || stock > 0);
        }).length;
        this.setData({
          hasAccess: true,
          loading: false,
          shopName: shop.name || '当前店铺',
          stats: [
            { label: '制作中订单', value: String(makingOrders) },
            { label: '可点菜品', value: String(availableDishes) },
            { label: '菜品分类', value: String((categoryResult.categories || []).length) },
          ],
        });
        return;
      }
      this.setData({ hasAccess: false, loading: false });
    } catch (error) {
      wx.showToast({ title: '读取管理数据失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  openDishesPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'dishes' });
    wx.navigateTo({
      url: '/pages/admin-dishes/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开菜品管理失败', icon: 'none' });
      },
    });
  },
  openOrdersPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'orders' });
    wx.navigateTo({
      url: '/pages/admin-orders/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开订单管理失败', icon: 'none' });
      },
    });
  },
  openCategoriesPage() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'categories' });
    wx.navigateTo({
      url: '/pages/admin-categories/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开分类管理失败', icon: 'none' });
      },
    });
  },
  openShopSettings() {
    if (this.data.navigatingTarget) return;
    this.setData({ navigatingTarget: 'settings' });
    wx.navigateTo({
      url: '/pages/admin-shop-settings/index',
      fail: () => {
        this.setData({ navigatingTarget: '' });
        wx.showToast({ title: '打开店铺设置失败', icon: 'none' });
      },
    });
  },
});
