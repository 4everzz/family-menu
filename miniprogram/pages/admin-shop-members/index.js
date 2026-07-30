const { ensureCurrentShop } = require('../../utils/shop-context');

function makeAvatarText(nickname) {
  const text = String(nickname || '微').trim();
  return text ? text.slice(0, 1) : '微';
}

function decorateMemberCard(item) {
  return {
    ...item,
    avatarText: makeAvatarText(item && item.nickname),
  };
}

Page({
  data: {
    loading: true,
    hasAccess: false,
    shopName: '',
    members: [],
    keyword: '',
    searchResults: [],
    searching: false,
    operatingUserId: '',
    canGrantOwner: false,
    loadedAt: 0,
  },
  onLoad() {
    this.loadMembers();
  },
  onShow() {
    if (this.data.loadedAt && Date.now() - this.data.loadedAt > 60 * 1000) this.loadMembers();
  },
  async callShopAdmin(action, payload = {}) {
    const shop = await ensureCurrentShop();
    const response = await wx.cloud.callFunction({
      name: 'shop-admin',
      data: { action, ...payload, shopId: shop.id },
    });
    return response.result || {};
  },
  async loadMembers() {
    this.setData({ loading: true });
    try {
      const shop = await ensureCurrentShop();
      const result = await this.callShopAdmin('listShopMembers');
      if (!result.ok) {
        this.setData({ hasAccess: false, loading: false, members: [] });
        return;
      }
      this.setData({
        hasAccess: true,
        loading: false,
        shopName: shop.name || '当前店铺',
        members: (result.members || []).map(decorateMemberCard),
        canGrantOwner: result.canGrantOwner === true,
        loadedAt: Date.now(),
      });
    } catch (error) {
      wx.showToast({ title: '读取成员失败', icon: 'none' });
      this.setData({ loading: false, hasAccess: false });
    }
  },
  updateKeyword(event) {
    this.setData({ keyword: event.detail.value });
  },
  async searchUsers() {
    const keyword = this.data.keyword.trim();
    if (!keyword) {
      wx.showToast({ title: '请输入系统ID或昵称', icon: 'none' });
      return;
    }
    this.setData({ searching: true });
    try {
      const result = await this.callShopAdmin('searchUsers', { keyword });
      if (!result.ok) throw new Error(result.message || '搜索失败');
      this.setData({ searchResults: (result.users || []).map(decorateMemberCard) });
    } catch (error) {
      wx.showToast({ title: error.message || '搜索失败', icon: 'none' });
    } finally {
      this.setData({ searching: false });
    }
  },
  clearSearch() {
    this.setData({ keyword: '', searchResults: [] });
  },
  async grantSelfOwner() {
    if (this.data.operatingUserId) return;
    this.setData({ operatingUserId: 'self' });
    try {
      const result = await this.callShopAdmin('grantSelfOwner');
      if (!result.ok) throw new Error(result.message || '设置失败');
      getApp().globalData.membersUpdatedAt = Date.now();
      wx.showToast({ title: '已设为一级管理员', icon: 'success' });
      await this.loadMembers();
    } catch (error) {
      wx.showToast({ title: error.message || '设置失败', icon: 'none' });
    } finally {
      this.setData({ operatingUserId: '' });
    }
  },
  grantStaff(event) {
    this.confirmGrant(event.currentTarget.dataset.id, 'store_staff', '二级管理员');
  },
  grantOwner(event) {
    this.confirmGrant(event.currentTarget.dataset.id, 'store_owner', '一级管理员');
  },
  confirmGrant(userId, role, roleName) {
    if (!userId || this.data.operatingUserId) return;
    wx.showModal({
      title: `设置为${roleName}`,
      content: role === 'store_owner'
        ? '一级管理员可以管理本店并设置二级管理员，请确认这是店铺负责人。'
        : '二级管理员可以处理本店日常管理，但不能继续授权其他管理员。',
      confirmText: '确认授权',
      confirmColor: '#DC2626',
      success: async (modal) => {
        if (!modal.confirm) return;
        await this.grantMember(userId, role);
      },
    });
  },
  async grantMember(userId, role) {
    this.setData({ operatingUserId: userId });
    try {
      const result = await this.callShopAdmin('grantShopMember', { userId, role });
      if (!result.ok) throw new Error(result.message || '授权失败');
      getApp().globalData.membersUpdatedAt = Date.now();
      wx.showToast({ title: '授权成功', icon: 'success' });
      await this.loadMembers();
      if (this.data.keyword.trim()) await this.searchUsers();
    } catch (error) {
      wx.showToast({ title: error.message || '授权失败', icon: 'none' });
    } finally {
      this.setData({ operatingUserId: '' });
    }
  },
  revokeMember(event) {
    const userId = event.currentTarget.dataset.id;
    const role = event.currentTarget.dataset.role;
    if (!userId || this.data.operatingUserId) return;
    wx.showModal({
      title: '撤销成员权限',
      content: role === 'store_owner'
        ? '确定撤销该一级管理员吗？只有超级管理员可以执行此操作。'
        : '确定撤销该二级管理员吗？撤销后将不能进入本店管理页。',
      confirmText: '确认撤销',
      confirmColor: '#DC2626',
      success: async (modal) => {
        if (!modal.confirm) return;
        await this.doRevokeMember(userId);
      },
    });
  },
  async doRevokeMember(userId) {
    this.setData({ operatingUserId: userId });
    try {
      const result = await this.callShopAdmin('revokeShopMember', { userId });
      if (!result.ok) throw new Error(result.message || '撤销失败');
      getApp().globalData.membersUpdatedAt = Date.now();
      wx.showToast({ title: '已撤销', icon: 'success' });
      await this.loadMembers();
      if (this.data.keyword.trim()) await this.searchUsers();
    } catch (error) {
      wx.showToast({ title: error.message || '撤销失败', icon: 'none' });
    } finally {
      this.setData({ operatingUserId: '' });
    }
  },
});
