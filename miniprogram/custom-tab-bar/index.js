Component({
  data: {
    selected: 0,
    tabs: [
      { text: '点菜', path: '/pages/menu/index', iconPath: '/assets/tab-menu.png', selectedIconPath: '/assets/tab-menu-active.png' },
      { text: '订单', path: '/pages/orders/index', iconPath: '/assets/tab-orders.png', selectedIconPath: '/assets/tab-orders-active.png' },
      { text: '我的', path: '/pages/profile/index', iconPath: '/assets/tab-profile.png', selectedIconPath: '/assets/tab-profile-active.png' },
    ],
  },
  methods: {
    switchTab(event) {
      const { index, path } = event.currentTarget.dataset;
      this.setData({ selected: Number(index) });
      wx.switchTab({ url: path });
    },
  },
});
