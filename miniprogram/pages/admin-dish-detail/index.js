const SPICE_LEVELS = ['不辣', '微辣', '正常辣', '特辣'];

function makeSpiceChoices(options) {
  return SPICE_LEVELS.map((label) => ({ label, selected: options.includes(label) }));
}

Page({
  data: {
    id: '',
    mode: 'edit',
    loading: true,
    hasAccess: false,
    dish: null,
    categoryName: '',
    categories: [],
    spiceLevels: SPICE_LEVELS,
    newSpiceChoices: makeSpiceChoices([]),
    editSpiceChoices: makeSpiceChoices([]),
    categoryIndex: 0,
    newDish: {
      name: '',
      category: '',
      price: '',
      description: '',
      imageFileId: '',
      spiceOptions: [],
      defaultSpice: '',
    },
    editDraft: {
      name: '',
      category: '',
      price: '',
      description: '',
      imageFileId: '',
      spiceOptions: [],
      defaultSpice: '',
      enabled: true,
      manualSoldOut: false,
      dailyStock: '10',
      stock: '10',
    },
    draftStatusText: '在售',
    draftStatusClass: '',
    isSubmitting: false,
    imageUploading: false,
    savingDetails: false,
    deleting: false,
  },
  onLoad(options) {
    if (options.mode === 'create') {
      wx.setNavigationBarTitle({ title: '新增菜品' });
      this.setData({ mode: 'create' });
      this.loadCategoriesForCreate();
      return;
    }
    if (!options.id) {
      wx.navigateBack();
      return;
    }
    this.setData({ id: options.id });
    this.loadDish();
  },
  async callAdmin(action, payload = {}) {
    const response = await wx.cloud.callFunction({
      name: 'admin-menu',
      data: { action, ...payload },
    });
    return response.result || {};
  },
  getDraftStatus(draft) {
    const isOffline = draft.enabled === false || draft.manualSoldOut === true || Number(draft.stock) <= 0;
    return {
      text: draft.enabled === false ? '已下架' : ((draft.manualSoldOut === true || Number(draft.stock) <= 0) ? '已售罄' : '在售'),
      className: isOffline ? 'is-offline' : '',
    };
  },
  setEditDraft(editDraft, extra = {}) {
    const status = this.getDraftStatus(editDraft);
    this.setData({
      editDraft,
      draftStatusText: status.text,
      draftStatusClass: status.className,
      ...extra,
    });
  },
  async loadCategoriesForCreate() {
    this.setData({ loading: true });
    try {
      const result = await this.callAdmin('listCategories');
      if (!result.ok) {
        this.setData({ hasAccess: false, loading: false });
        return;
      }
      const categories = result.categories;
      this.setData({
        hasAccess: true,
        loading: false,
        categories,
        categoryIndex: 0,
        newDish: { ...this.data.newDish, category: categories[0] ? categories[0].id : '' },
      });
    } catch (error) {
      wx.showToast({ title: '读取分类失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  async loadDish() {
    this.setData({ loading: true });
    try {
      const [dishResult, categoryResult] = await Promise.all([
        this.callAdmin('listDishes'),
        this.callAdmin('listCategories'),
      ]);
      if (!dishResult.ok || !categoryResult.ok) {
        this.setData({ hasAccess: false, loading: false });
        return;
      }
      const dish = dishResult.dishes.find((item) => item.id === this.data.id);
      if (!dish) {
        wx.showToast({ title: '菜品不存在', icon: 'none' });
        wx.navigateBack();
        return;
      }
      const category = categoryResult.categories.find((item) => item.id === dish.category);
      const dailyStock = Number.isInteger(dish.dailyStock) && dish.dailyStock >= 0 ? dish.dailyStock : 10;
      const stock = Number.isInteger(dish.stock) && dish.stock >= 0 ? dish.stock : dailyStock;
      const normalizedDish = { ...dish, dailyStock, stock, manualSoldOut: dish.manualSoldOut === true };
      const editDraft = {
        name: normalizedDish.name || '',
        category: normalizedDish.category || '',
        price: String(normalizedDish.price),
        description: normalizedDish.description || '',
        imageFileId: normalizedDish.imageFileId || '',
        spiceOptions: normalizedDish.spiceOptions || [],
        defaultSpice: normalizedDish.defaultSpice || '',
        enabled: normalizedDish.enabled !== false,
        manualSoldOut: normalizedDish.manualSoldOut === true,
        dailyStock: String(dailyStock),
        stock: String(stock),
      };
      const draftStatus = this.getDraftStatus(editDraft);
      this.setData({
        hasAccess: true,
        loading: false,
        dish: normalizedDish,
        categoryName: category ? category.name : dish.category,
        categories: categoryResult.categories,
        categoryIndex: Math.max(0, categoryResult.categories.findIndex((item) => item.id === dish.category)),
        editDraft,
        editSpiceChoices: makeSpiceChoices(normalizedDish.spiceOptions || []),
        draftStatusText: draftStatus.text,
        draftStatusClass: draftStatus.className,
      });
    } catch (error) {
      wx.showToast({ title: '读取菜品失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },
  updateNewDish(event) {
    const { field } = event.currentTarget.dataset;
    this.setData({ newDish: { ...this.data.newDish, [field]: event.detail.value } });
  },
  selectNewDishCategory(event) {
    const categoryIndex = Number(event.detail.value);
    const category = this.data.categories[categoryIndex];
    this.setData({
      categoryIndex,
      newDish: { ...this.data.newDish, category: category ? category.id : '' },
    });
  },
  toggleDishSpice(event) {
    const { mode, value } = event.currentTarget.dataset;
    const draftKey = mode === 'create' ? 'newDish' : 'editDraft';
    const draft = this.data[draftKey];
    const spiceOptions = draft.spiceOptions.includes(value)
      ? draft.spiceOptions.filter((item) => item !== value)
      : [...draft.spiceOptions, value];
    const defaultSpice = spiceOptions.includes(draft.defaultSpice) ? draft.defaultSpice : (spiceOptions[0] || '');
    const choiceKey = mode === 'create' ? 'newSpiceChoices' : 'editSpiceChoices';
    const nextDraft = { ...draft, spiceOptions, defaultSpice };
    if (mode === 'edit') {
      this.setEditDraft(nextDraft, { [choiceKey]: makeSpiceChoices(spiceOptions) });
      return;
    }
    this.setData({ [draftKey]: nextDraft, [choiceKey]: makeSpiceChoices(spiceOptions) });
  },
  selectDefaultSpice(event) {
    const { mode, value } = event.currentTarget.dataset;
    const draftKey = mode === 'create' ? 'newDish' : 'editDraft';
    const draft = this.data[draftKey];
    if (!draft.spiceOptions.includes(value)) return;
    const nextDraft = { ...draft, defaultSpice: value };
    if (mode === 'edit') {
      this.setEditDraft(nextDraft);
      return;
    }
    this.setData({ [draftKey]: nextDraft });
  },
  async chooseDishImage(event) {
    const mode = event.currentTarget.dataset.mode;
    if (this.data.imageUploading) return;
    try {
      const selection = await wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'] });
      const filePath = selection.tempFiles && selection.tempFiles[0] && selection.tempFiles[0].tempFilePath;
      if (!filePath) return;
      const extension = (filePath.match(/\.([a-zA-Z0-9]+)$/) || [])[1] || 'jpg';
      this.setData({ imageUploading: true });
      const uploaded = await wx.cloud.uploadFile({
        cloudPath: `dish-images/${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${extension.toLowerCase()}`,
        filePath,
      });
      if (!uploaded.fileID) throw new Error('图片上传失败');
      if (mode === 'create') {
        this.setData({ newDish: { ...this.data.newDish, imageFileId: uploaded.fileID } });
      } else {
        this.setEditDraft({ ...this.data.editDraft, imageFileId: uploaded.fileID });
      }
      wx.showToast({ title: '图片已上传', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: error.message || '图片上传失败', icon: 'none' });
    } finally {
      this.setData({ imageUploading: false });
    }
  },
  cancelCreate() {
    wx.navigateBack();
  },
  async submitNewDish() {
    const { newDish } = this.data;
    const name = newDish.name.trim();
    const description = newDish.description.trim();
    const price = Number(newDish.price);
    if (!name || !newDish.category || !Number.isFinite(price) || price <= 0) {
      wx.showToast({ title: '请填写菜名、分类和有效价格', icon: 'none' });
      return;
    }
    this.setData({ isSubmitting: true });
    try {
      const result = await this.callAdmin('addDish', {
        name,
        category: newDish.category,
        price,
        description,
        imageFileId: newDish.imageFileId,
        spiceOptions: newDish.spiceOptions,
        defaultSpice: newDish.defaultSpice,
      });
      if (!result.ok) throw new Error(result.message || '新增失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      wx.showToast({ title: '菜品已新增', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 500);
    } catch (error) {
      wx.showToast({ title: '新增失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
  updateEditDraft(event) {
    const { field } = event.currentTarget.dataset;
    this.setEditDraft({ ...this.data.editDraft, [field]: event.detail.value });
  },
  selectEditCategory(event) {
    const categoryIndex = Number(event.detail.value);
    const category = this.data.categories[categoryIndex];
    this.setEditDraft({ ...this.data.editDraft, category: category ? category.id : '' }, { categoryIndex });
  },
  async saveDishDetails() {
    const { editDraft } = this.data;
    const name = editDraft.name.trim();
    const price = Number(editDraft.price);
    const dailyStock = Number(editDraft.dailyStock);
    const stock = Number(editDraft.stock);
    if (!name || !editDraft.category || !Number.isFinite(price) || price <= 0) {
      wx.showToast({ title: '请填写菜名、分类和有效价格', icon: 'none' });
      return;
    }
    if (!Number.isInteger(dailyStock) || !Number.isInteger(stock) || dailyStock < 0 || stock < 0 || stock > dailyStock) {
      wx.showToast({ title: '库存需为非负整数，且剩余不超过每日份数', icon: 'none' });
      return;
    }
    this.setData({ savingDetails: true });
    try {
      const result = await this.callAdmin('updateDish', {
        id: this.data.id,
        name,
        category: editDraft.category,
        price,
        description: editDraft.description.trim(),
        imageFileId: editDraft.imageFileId,
        spiceOptions: editDraft.spiceOptions,
        defaultSpice: editDraft.defaultSpice,
        enabled: editDraft.enabled !== false,
        manualSoldOut: editDraft.manualSoldOut === true,
        dailyStock,
        stock,
      });
      if (!result.ok) throw new Error(result.message || '保存失败');
      const category = this.data.categories.find((item) => item.id === result.dish.category);
      getApp().globalData.menuUpdatedAt = Date.now();
      const nextDraft = {
        name: result.dish.name,
        category: result.dish.category,
        price: String(result.dish.price),
        description: result.dish.description,
        imageFileId: result.dish.imageFileId || '',
        spiceOptions: result.dish.spiceOptions || [],
        defaultSpice: result.dish.defaultSpice || '',
        enabled: result.dish.enabled !== false,
        manualSoldOut: result.dish.manualSoldOut === true,
        dailyStock: String(result.dish.dailyStock),
        stock: String(result.dish.stock),
      };
      this.setEditDraft(nextDraft, {
        dish: { ...this.data.dish, ...result.dish },
        categoryName: category ? category.name : result.dish.category,
        editSpiceChoices: makeSpiceChoices(result.dish.spiceOptions || []),
      });
      wx.showToast({ title: '菜品已保存', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: '保存失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ savingDetails: false });
    }
  },
  async toggleDishEnabled() {
    this.setEditDraft({ ...this.data.editDraft, enabled: this.data.editDraft.enabled === false });
  },
  async toggleManualSoldOut() {
    this.setEditDraft({ ...this.data.editDraft, manualSoldOut: this.data.editDraft.manualSoldOut !== true });
  },
  async deleteDish() {
    if (this.data.deleting) return;
    const modal = await new Promise((resolve) => wx.showModal({
      title: '永久删除菜品',
      content: `确定永久删除“${this.data.dish.name}”吗？删除后不可恢复。`,
      confirmText: '确认删除',
      confirmColor: '#DC2626',
      success: resolve,
    }));
    if (!modal.confirm) return;
    this.setData({ deleting: true });
    try {
      const result = await this.callAdmin('deleteDish', { id: this.data.id });
      if (!result.ok) throw new Error(result.message || '删除失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      wx.showToast({ title: '菜品已删除', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 400);
    } catch (error) {
      wx.showToast({ title: error.message || '删除失败，请检查权限', icon: 'none' });
      this.setData({ deleting: false });
    }
  },
});
