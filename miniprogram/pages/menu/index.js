const dishes = [
  { id: 'd1', category: 'recommended', name: '宫保鸡丁', description: '鲜香微辣，花生酥脆', price: 38, emoji: '🍗', color: '#FEE2E2' },
  { id: 'd2', category: 'recommended', name: '番茄炒蛋', description: '酸甜软嫩，家常下饭', price: 22, emoji: '🍅', color: '#FFEDD5' },
  { id: 'd3', category: 'home', name: '红烧肉', description: '酱香浓郁，软糯入味', price: 58, emoji: '🥩', color: '#FDE68A' },
  { id: 'd4', category: 'home', name: '凉拌黄瓜', description: '清爽开胃，微微回甘', price: 16, emoji: '🥒', color: '#DCFCE7' },
  { id: 'd5', category: 'soup', name: '酸辣汤', description: '暖胃开胃，酸辣适中', price: 18, emoji: '🥣', color: '#FCE7F3' },
  { id: 'd6', category: 'staple', name: '扬州炒饭', description: '粒粒分明，配料丰富', price: 22, emoji: '🍚', color: '#FEF3C7' },
];

Page({
  data: {
    categories: [
      { id: 'all', name: '全部' },
      { id: 'recommended', name: '推荐' },
      { id: 'home', name: '家常菜' },
      { id: 'soup', name: '汤品' },
      { id: 'staple', name: '主食' },
    ],
    activeCategory: 'all',
    dishes: [],
    cartCount: 0,
  },
  onShow() {
    this.renderDishes();
  },
  selectCategory(event) {
    this.setData({ activeCategory: event.currentTarget.dataset.id }, () => this.renderDishes());
  },
  addDish(event) {
    const id = event.currentTarget.dataset.id;
    const app = getApp();
    const dish = dishes.find((item) => item.id === id);
    const cartItem = app.globalData.cart.find((item) => item.id === id);
    if (cartItem) {
      cartItem.quantity += 1;
    } else {
      app.globalData.cart.push({ ...dish, quantity: 1 });
    }
    this.renderDishes();
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },
  goCart() {
    wx.switchTab({ url: '/pages/cart/index' });
  },
  renderDishes() {
    const app = getApp();
    const filtered = this.data.activeCategory === 'all'
      ? dishes
      : dishes.filter((item) => item.category === this.data.activeCategory);
    const rendered = filtered.map((dish) => {
      const cartItem = app.globalData.cart.find((item) => item.id === dish.id);
      return { ...dish, quantity: cartItem ? cartItem.quantity : 0 };
    });
    const cartCount = app.globalData.cart.reduce((total, item) => total + item.quantity, 0);
    this.setData({ dishes: rendered, cartCount });
  },
});
