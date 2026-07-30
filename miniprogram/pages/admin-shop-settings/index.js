const { ensureCurrentShop } = require('../../utils/shop-context');
const drawQrcode = require('./weapp-qrcode');

function getChinaDateKey() {
  const chinaTime = new Date(Date.now() + 8 * 60 * 60 * 1000);
  const year = chinaTime.getUTCFullYear();
  const month = String(chinaTime.getUTCMonth() + 1).padStart(2, '0');
  const day = String(chinaTime.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

Page({
  data: {
    loading: true,
    saving: false,
    rotating: false,
    rotateConfirming: false,
    shopName: '',
    acceptingOrders: true,
    orderEntryMode: 'store_entry',
    changingEntryMode: false,
    closedDates: [],
    selectedDate: getChinaDateKey(),
    currentShopCode: '',
    latestShopCode: '',
    tables: [],
    tableName: '',
    addingTable: false,
    tableActionId: '',
    latestTableCode: '',
    latestTableName: '',
    showTableQr: false,
    qrTitle: '',
    qrContent: '',
    qrCanvasSize: 260,
    loadedAt: 0,
  },
  onLoad() {
    this.loadSettings();
  },
  onShow() {
    if (this.data.loadedAt && Date.now() - this.data.loadedAt > 60 * 1000) this.loadSettings();
  },
  async callShopAdmin(action, payload = {}) {
    const shop = await ensureCurrentShop();
    const response = await wx.cloud.callFunction({
      name: 'shop-admin',
      data: { action, ...payload, shopId: shop.id },
    });
    return response.result || {};
  },
  async loadSettings() {
    this.setData({ loading: true });
    try {
      const [result, tableResult] = await Promise.all([
        this.callShopAdmin('getShopSettings'),
        this.callShopAdmin('listTables'),
      ]);
      if (!result.ok || !result.settings || !tableResult.ok) throw new Error(result.message || tableResult.message || '读取店铺设置失败');
      this.setData({
        loading: false,
        shopName: result.settings.name,
        currentShopCode: result.settings.displayShopCode || '',
        acceptingOrders: result.settings.acceptingOrders !== false,
        orderEntryMode: result.settings.orderEntryMode === 'table_required' ? 'table_required' : 'store_entry',
        closedDates: result.settings.closedDates || [],
        tables: tableResult.tables || [],
        loadedAt: Date.now(),
      });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: error.message || '读取店铺设置失败', icon: 'none' });
    }
  },
  toggleAcceptingOrders(event) {
    this.setData({ acceptingOrders: event.detail.value === true });
  },
  changeOrderEntryMode(event) {
    const orderEntryMode = event.currentTarget.dataset.mode;
    if (!['store_entry', 'table_required'].includes(orderEntryMode)
      || orderEntryMode === this.data.orderEntryMode
      || this.data.changingEntryMode) return;
    const isTableRequired = orderEntryMode === 'table_required';
    wx.showModal({
      title: isTableRequired ? '启用桌码点餐' : '启用店铺码点餐',
      content: isTableRequired
        ? '启用后，顾客必须扫描有效桌码才能提交订单。'
        : '启用后，顾客扫描店铺通用码即可进入并提交订单。',
      confirmText: '确认切换',
      confirmColor: '#DC2626',
      success: async (choice) => {
        if (!choice.confirm) return;
        this.setData({ changingEntryMode: true });
        try {
          const result = await this.callShopAdmin('updateOrderEntryMode', { orderEntryMode });
          if (!result.ok || !result.settings) throw new Error(result.message || '切换入口方式失败');
          this.setData({ orderEntryMode: result.settings.orderEntryMode });
          wx.showToast({ title: '入口方式已更新', icon: 'success' });
        } catch (error) {
          wx.showToast({ title: error.message || '切换入口方式失败', icon: 'none' });
        } finally {
          this.setData({ changingEntryMode: false });
        }
      },
    });
  },
  changeDate(event) {
    this.setData({ selectedDate: event.detail.value });
  },
  addClosedDate() {
    const date = this.data.selectedDate;
    if (this.data.closedDates.includes(date)) {
      wx.showToast({ title: '该日期已在列表中', icon: 'none' });
      return;
    }
    this.setData({ closedDates: [...this.data.closedDates, date].sort() });
  },
  removeClosedDate(event) {
    const date = event.currentTarget.dataset.date;
    this.setData({ closedDates: this.data.closedDates.filter((item) => item !== date) });
  },
  async saveOperatingRules() {
    if (this.data.saving) return;
    this.setData({ saving: true });
    try {
      const result = await this.callShopAdmin('updateOperatingRules', {
        acceptingOrders: this.data.acceptingOrders,
        closedDates: this.data.closedDates,
      });
      if (!result.ok || !result.settings) throw new Error(result.message || '保存失败');
      this.setData({
        acceptingOrders: result.settings.acceptingOrders !== false,
        closedDates: result.settings.closedDates || [],
      });
      wx.showToast({ title: '营业设置已保存', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: error.message || '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },
  rotateShopCode() {
    if (this.data.rotating) return;
    if (!this.data.rotateConfirming) {
      this.setData({ rotateConfirming: true });
      this.rotateTimer = setTimeout(() => this.setData({ rotateConfirming: false }), 8000);
      return;
    }
    if (this.rotateTimer) clearTimeout(this.rotateTimer);
    this.setData({ rotating: true, rotateConfirming: false });
    this.callShopAdmin('rotateShopCode').then((result) => {
      if (!result.ok || !result.shopCode) throw new Error(result.message || '重置店铺码失败');
      this.setData({ rotating: false, currentShopCode: result.shopCode, latestShopCode: result.shopCode });
      wx.setClipboardData({
        data: result.shopCode,
        success: () => wx.showToast({ title: '新店铺码已复制', icon: 'success' }),
        fail: () => wx.showToast({ title: '请手动保存新店铺码', icon: 'none' }),
      });
    }).catch((error) => {
      wx.showToast({ title: error.message || '重置店铺码失败', icon: 'none' });
      this.setData({ rotating: false, rotateConfirming: false });
    });
  },
  copyLatestShopCode() {
    const shopCode = this.data.latestShopCode || this.data.currentShopCode;
    if (!shopCode) return;
    wx.setClipboardData({
      data: shopCode,
      success: () => wx.showToast({ title: '店铺码已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }),
    });
  },
  copyLatestShopQrContent() {
    const shopCode = this.data.latestShopCode || this.data.currentShopCode;
    if (!shopCode) return;
    wx.setClipboardData({
      data: `SHOP:${shopCode}`,
      success: () => wx.showToast({ title: '二维码内容已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }),
    });
  },
  openShopQr() {
    const shopCode = this.data.latestShopCode || this.data.currentShopCode;
    if (!shopCode) return;
    this.openCodeQr('店铺码二维码', `SHOP:${shopCode}`);
  },
  updateTableName(event) {
    this.setData({ tableName: event.detail.value });
  },
  async addTable() {
    const name = this.data.tableName.trim();
    if (!name || this.data.addingTable) return;
    this.setData({ addingTable: true });
    try {
      const result = await this.callShopAdmin('addTable', { name });
      if (!result.ok || !result.table || !result.tableCode) throw new Error(result.message || '新增桌位失败');
      this.setData({
        tableName: '',
        latestTableName: result.table.name,
        latestTableCode: result.tableCode,
        tables: [...this.data.tables, result.table].sort((left, right) => left.sort - right.sort || left.name.localeCompare(right.name, 'zh-CN')),
      });
      wx.setClipboardData({ data: result.tableCode, success: () => wx.showToast({ title: '桌位码已复制', icon: 'success' }) });
    } catch (error) {
      wx.showToast({ title: error.message || '新增桌位失败', icon: 'none' });
    } finally {
      this.setData({ addingTable: false });
    }
  },
  async toggleTableEnabled(event) {
    const id = event.currentTarget.dataset.id;
    const enabled = event.currentTarget.dataset.enabled === true || event.currentTarget.dataset.enabled === 'true';
    if (!id || this.data.tableActionId) return;
    this.setData({ tableActionId: id });
    try {
      const result = await this.callShopAdmin('updateTableEnabled', { id, enabled });
      if (!result.ok || !result.table) throw new Error(result.message || '更新桌位失败');
      this.setData({ tables: this.data.tables.map((table) => (table.id === id ? result.table : table)) });
    } catch (error) {
      wx.showToast({ title: error.message || '更新桌位失败', icon: 'none' });
    } finally {
      this.setData({ tableActionId: '' });
    }
  },
  rotateTableCode(event) {
    const id = event.currentTarget.dataset.id;
    const name = event.currentTarget.dataset.name;
    if (!id || this.data.tableActionId) return;
    wx.showModal({
      title: '重置桌位码',
      content: `重置后，${name}的原桌码将立即失效。`,
      confirmText: '确认重置',
      confirmColor: '#DC2626',
      success: async (choice) => {
        if (!choice.confirm) return;
        this.setData({ tableActionId: id });
        try {
          const result = await this.callShopAdmin('rotateTableCode', { id });
          if (!result.ok || !result.tableCode) throw new Error(result.message || '重置桌位码失败');
          this.setData({
            latestTableName: name,
            latestTableCode: result.tableCode,
            tables: this.data.tables.map((table) => (table.id === id ? { ...table, displayCode: result.tableCode } : table)),
          });
          wx.setClipboardData({ data: result.tableCode, success: () => wx.showToast({ title: '新桌位码已复制', icon: 'success' }) });
        } catch (error) {
          wx.showToast({ title: error.message || '重置桌位码失败', icon: 'none' });
        } finally {
          this.setData({ tableActionId: '' });
        }
      },
    });
  },
  copyLatestTableCode() {
    if (!this.data.latestTableCode) return;
    wx.setClipboardData({
      data: this.data.latestTableCode,
      success: () => wx.showToast({ title: '桌位码已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }),
    });
  },
  copyTableCode(event) {
    const code = event.currentTarget.dataset.code;
    if (!code) return;
    wx.setClipboardData({
      data: code,
      success: () => wx.showToast({ title: '桌位码已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败，请重试', icon: 'none' }),
    });
  },
  openExistingTableQr(event) {
    const code = event.currentTarget.dataset.code;
    const name = event.currentTarget.dataset.name || '桌位';
    if (!code) return;
    this.openCodeQr(`${name}桌码`, `TABLE:${code}`);
  },
  openTableQr() {
    const tableCode = this.data.latestTableCode;
    if (!tableCode) return;
    this.openCodeQr(`${this.data.latestTableName}桌码`, `TABLE:${tableCode}`);
  },
  openCodeQr(title, qrContent) {
    const systemInfo = wx.getSystemInfoSync ? wx.getSystemInfoSync() : { windowWidth: 375 };
    const qrCanvasSize = Math.floor(Math.min(systemInfo.windowWidth - 88, systemInfo.windowWidth * 0.7));
    this.setData({
      showTableQr: true,
      qrTitle: title,
      qrContent,
      qrCanvasSize,
    }, () => {
      drawQrcode({
        width: qrCanvasSize,
        height: qrCanvasSize,
        canvasId: 'table-qrcode',
        ctx: wx.createCanvasContext('table-qrcode'),
        text: qrContent,
        foreground: '#450A0A',
        background: '#FFFFFF',
      });
    });
  },
  closeTableQr() {
    this.setData({ showTableQr: false });
  },
  stopQrTap() {},
  onHide() {
    if (this.rotateTimer) clearTimeout(this.rotateTimer);
    this.rotateTimer = null;
  },
});
