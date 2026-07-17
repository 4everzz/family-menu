Page({
  data: {
    loading: true,
    hasAccess: false,
    dishes: [],
    categories: [],
    categoryIndex: 0,
    activeCategory: 'all',
    activeCategoryName: '全部',
    keyword: '',
    filteredDishes: [],
    gridHeight: 900,
    lastMenuUpdatedAt: 0,
  },
  onLoad() {
    this.updateGridHeight();
    this.loadDishes();
  },
  onShow() {
    const updatedAt = getApp().globalData.menuUpdatedAt;
    if (updatedAt && updatedAt !== this.data.lastMenuUpdatedAt) {
      this.setData({ lastMenuUpdatedAt: updatedAt });
      this.loadDishes();
    }
  },
  onResize() {
    this.updateGridHeight();
  },
  updateGridHeight() {
    const { windowHeight, windowWidth } = wx.getSystemInfoSync();
    const rpxPerPixel = 750 / windowWidth;
    const gridHeight = Math.max(460, Math.floor(windowHeight * rpxPerPixel - 340));
    this.setData({ gridHeight });
  },
  async callAdmin(action, payload = {}) {
    const response = await wx.cloud.callFunction({
      name: 'admin-menu',
      data: { action, ...payload },
    });
    return response.result || {};
  },
  async loadDishes() {
    this.setData({ loading: true });
    try {
      const inventoryResult = await this.callAdmin('initializeDishInventory');
      if (!inventoryResult.ok) {
        this.setData({ hasAccess: false, loading: false });
        return;
      }
      const [dishResult, categoryResult] = await Promise.all([
        this.callAdmin('listDishes'),
        this.callAdmin('listCategories'),
      ]);
      if (!dishResult.ok || !categoryResult.ok) {
        this.setData({ hasAccess: false, loading: false });
        return;
      }
      const categories = [
        { id: 'all', name: '全部' },
        ...categoryResult.categories.filter((item) => item.id !== 'all'),
      ];
      this.setData({
        hasAccess: true,
        loading: false,
        dishes: dishResult.dishes,
        categories,
        categoryIndex: 0,
        activeCategory: 'all',
      }, () => this.renderDishes());
    } catch (error) {
      wx.showToast({ title: '读取菜品失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  selectCategory(event) {
    const categoryIndex = Number(event.detail.value);
    const category = this.data.categories[categoryIndex];
    this.setData({
      categoryIndex,
      activeCategory: category ? category.id : 'all',
    }, () => this.renderDishes());
  },
  updateKeyword(event) {
    this.setData({ keyword: event.detail.value }, () => this.renderDishes());
  },
  clearKeyword() {
    this.setData({ keyword: '' }, () => this.renderDishes());
  },
  renderDishes() {
    const categoryNames = this.data.categories.reduce((result, item) => {
      result[item.id] = item.name;
      return result;
    }, {});
    const keyword = this.data.keyword.trim();
    const filteredDishes = this.data.dishes.filter((item) => {
      const matchesCategory = this.data.activeCategory === 'all' || item.category === this.data.activeCategory;
      const matchesKeyword = !keyword
        || item.name.includes(keyword)
        || (categoryNames[item.category] || '').includes(keyword);
      return matchesCategory && matchesKeyword;
    }).map((item) => {
      const isSoldOut = item.manualSoldOut === true || Number(item.stock) <= 0;
      return {
        ...item,
        statusText: item.enabled === false ? '已下架' : (isSoldOut ? '已售罄' : '在售'),
        statusClass: item.enabled === false || isSoldOut ? 'is-offline' : '',
      };
    });
    this.setData({
      filteredDishes,
      activeCategoryName: categoryNames[this.data.activeCategory] || '全部',
    });
  },
  openDish(event) {
    wx.navigateTo({ url: `/pages/admin-dish-detail/index?id=${event.currentTarget.dataset.id}` });
  },
  openCreateDish() {
    wx.navigateTo({ url: '/pages/admin-dish-detail/index?mode=create' });
  },
});
