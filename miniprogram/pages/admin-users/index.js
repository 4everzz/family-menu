const { callAuth, refreshCurrentUser } = require('../../utils/auth-store');

const ROLE_TEXT = { user: '普通用户', manager: '管理员', super_admin: '超级管理员' };

Page({
  data: { loading: true, users: [] },
  async onShow() {
    const currentUser = await refreshCurrentUser();
    if (!currentUser || currentUser.role !== 'super_admin') {
      wx.showToast({ title: '没有访问权限', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 350);
      return;
    }
    await this.loadUsers();
  },
  async loadUsers() {
    this.setData({ loading: true });
    try {
      const result = await callAuth('listUsers');
      if (!result.ok) throw new Error(result.message || '读取用户失败');
      this.setData({ users: (result.users || []).map((user) => ({
        ...user,
        avatarText: (user.nickname || '微').slice(0, 1),
        roleText: ROLE_TEXT[user.role] || ROLE_TEXT.user,
        actionText: user.role === 'user' ? '设为管理员' : '撤销管理员',
        statusText: user.enabled ? '正常使用' : '已停用',
      })) });
    } catch (error) {
      wx.showToast({ title: error.message || '读取用户失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
  async changeRole(event) {
    const { id, role } = event.currentTarget.dataset;
    if (role === 'super_admin') return;
    const nextRole = role === 'user' ? 'manager' : 'user';
    const label = nextRole === 'manager' ? '设为管理员' : '撤销管理员';
    const modal = await new Promise((resolve) => wx.showModal({ title: '确认操作', content: `确定${label}吗？`, success: resolve }));
    if (!modal.confirm) return;
    try {
      const result = await callAuth('updateUserRole', { id, role: nextRole });
      if (!result.ok) throw new Error(result.message || '更新权限失败');
      wx.showToast({ title: '权限已更新', icon: 'success' });
      await this.loadUsers();
    } catch (error) {
      wx.showToast({ title: error.message || '更新权限失败', icon: 'none' });
    }
  },
  async toggleEnabled(event) {
    const { id, enabled, role } = event.currentTarget.dataset;
    if (role === 'super_admin') return;
    const nextEnabled = enabled !== true;
    const label = nextEnabled ? '恢复账号' : '停用账号';
    const modal = await new Promise((resolve) => wx.showModal({ title: '确认操作', content: `确定${label}吗？`, success: resolve }));
    if (!modal.confirm) return;
    try {
      const result = await callAuth('updateUserEnabled', { id, enabled: nextEnabled });
      if (!result.ok) throw new Error(result.message || '更新账号状态失败');
      wx.showToast({ title: '账号状态已更新', icon: 'success' });
      await this.loadUsers();
    } catch (error) {
      wx.showToast({ title: error.message || '更新账号状态失败', icon: 'none' });
    }
  },
});
