Page({
  data: {
    loading: true,
    hasAccess: false,
    categories: [],
    newDraft: { name: '', sort: '99' },
    editId: '',
    editDraft: { name: '', sort: '' },
    isAdding: false,
    isSaving: false,
  },
  onShow() {
    this.loadCategories();
  },
  async callAdmin(action, payload = {}) {
    const response = await wx.cloud.callFunction({
      name: 'admin-menu',
      data: { action, ...payload },
    });
    return response.result || {};
  },
  async loadCategories() {
    this.setData({ loading: true });
    try {
      const result = await this.callAdmin('listCategories');
      if (!result.ok) {
        this.setData({ hasAccess: false, categories: [], loading: false });
        return;
      }
      const categories = (result.categories || []).map((item) => ({
        ...item,
        sortText: Number.isInteger(item.sort) ? String(item.sort) : '未设置',
        isEditing: item.id === this.data.editId,
      }));
      this.setData({ hasAccess: true, categories, loading: false });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: '读取分类失败，请稍后重试', icon: 'none' });
    }
  },
  updateNewDraft(event) {
    const { field } = event.currentTarget.dataset;
    this.setData({ newDraft: { ...this.data.newDraft, [field]: event.detail.value } });
  },
  updateEditDraft(event) {
    const { field } = event.currentTarget.dataset;
    this.setData({ editDraft: { ...this.data.editDraft, [field]: event.detail.value } });
  },
  selectCategory(event) {
    if (this.data.isAdding || this.data.isSaving) return;
    const category = this.data.categories.find((item) => item.id === event.currentTarget.dataset.id);
    if (!category) return;
    this.setData({
      editId: category.id,
      editDraft: { name: category.name, sort: Number.isInteger(category.sort) ? String(category.sort) : '99' },
      categories: this.data.categories.map((item) => ({ ...item, isEditing: item.id === category.id })),
    });
  },
  cancelEdit() {
    this.setData({
      editId: '',
      editDraft: { name: '', sort: '' },
      categories: this.data.categories.map((item) => ({ ...item, isEditing: false })),
    });
  },
  isValidDraft(draft) {
    const name = String(draft.name || '').trim();
    const sort = Number(draft.sort);
    return name && Number.isInteger(sort) && sort >= 0;
  },
  async addCategory() {
    if (!this.isValidDraft(this.data.newDraft) || this.data.isAdding || this.data.isSaving) {
      wx.showToast({ title: '请填写分类名称和非负整数排序', icon: 'none' });
      return;
    }
    this.setData({ isAdding: true });
    try {
      const result = await this.callAdmin('addCategory', {
        name: this.data.newDraft.name.trim(),
        sort: Number(this.data.newDraft.sort),
      });
      if (!result.ok) throw new Error(result.message || '新增分类失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({ newDraft: { name: '', sort: '99' } });
      wx.showToast({ title: '分类已新增', icon: 'success' });
      await this.loadCategories();
    } catch (error) {
      wx.showToast({ title: error.message || '新增分类失败', icon: 'none' });
    } finally {
      this.setData({ isAdding: false });
    }
  },
  async saveCategory() {
    if (!this.data.editId || !this.isValidDraft(this.data.editDraft) || this.data.isAdding || this.data.isSaving) {
      wx.showToast({ title: '请填写分类名称和非负整数排序', icon: 'none' });
      return;
    }
    this.setData({ isSaving: true });
    try {
      const result = await this.callAdmin('updateCategory', {
        id: this.data.editId,
        name: this.data.editDraft.name.trim(),
        sort: Number(this.data.editDraft.sort),
      });
      if (!result.ok) throw new Error(result.message || '保存分类失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      wx.showToast({ title: '分类已保存', icon: 'success' });
      this.cancelEdit();
      await this.loadCategories();
    } catch (error) {
      wx.showToast({ title: error.message || '保存分类失败', icon: 'none' });
    } finally {
      this.setData({ isSaving: false });
    }
  },
});
