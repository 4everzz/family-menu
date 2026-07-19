Page({
  data: {
    id: '',
    mode: 'edit',
    loading: true,
    hasAccess: false,
    dish: null,
    categoryName: '',
    categories: [],
    categoryIndex: 0,
    newDish: {
      name: '',
      category: '',
      price: '',
      description: '',
      imageFileId: '',
    },
    editDraft: {
      name: '',
      category: '',
      price: '',
      description: '',
      imageFileId: '',
    },
    isSubmitting: false,
    imageUploading: false,
    savingDetails: false,
    inventoryDraft: { dailyStock: '10', stock: '10' },
    savingInventory: false,
    savingStatus: false,
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
      this.setData({
        hasAccess: true,
        loading: false,
        dish: normalizedDish,
        categoryName: category ? category.name : dish.category,
        categories: categoryResult.categories,
        categoryIndex: Math.max(0, categoryResult.categories.findIndex((item) => item.id === dish.category)),
        editDraft: {
          name: normalizedDish.name || '',
          category: normalizedDish.category || '',
          price: String(normalizedDish.price),
          description: normalizedDish.description || '',
          imageFileId: normalizedDish.imageFileId || '',
        },
        inventoryDraft: { dailyStock: String(dailyStock), stock: String(stock) },
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
        this.setData({ editDraft: { ...this.data.editDraft, imageFileId: uploaded.fileID } });
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
    this.setData({ editDraft: { ...this.data.editDraft, [field]: event.detail.value } });
  },
  selectEditCategory(event) {
    const categoryIndex = Number(event.detail.value);
    const category = this.data.categories[categoryIndex];
    this.setData({
      categoryIndex,
      editDraft: { ...this.data.editDraft, category: category ? category.id : '' },
    });
  },
  async saveDishDetails() {
    const { editDraft } = this.data;
    const name = editDraft.name.trim();
    const price = Number(editDraft.price);
    if (!name || !editDraft.category || !Number.isFinite(price) || price <= 0) {
      wx.showToast({ title: '请填写菜名、分类和有效价格', icon: 'none' });
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
      });
      if (!result.ok) throw new Error(result.message || '保存失败');
      const category = this.data.categories.find((item) => item.id === result.dish.category);
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({
        dish: { ...this.data.dish, ...result.dish },
        categoryName: category ? category.name : result.dish.category,
        editDraft: {
          name: result.dish.name,
          category: result.dish.category,
          price: String(result.dish.price),
          description: result.dish.description,
          imageFileId: result.dish.imageFileId || '',
        },
      });
      wx.showToast({ title: '菜品资料已保存', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: '保存失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ savingDetails: false });
    }
  },
  async toggleDishEnabled() {
    const enabled = this.data.dish.enabled === false;
    this.setData({ savingStatus: true });
    try {
      const result = await this.callAdmin('updateDishEnabled', { id: this.data.id, enabled });
      if (!result.ok) throw new Error(result.message || '状态更新失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({ dish: { ...this.data.dish, enabled: result.enabled } });
      wx.showToast({ title: result.enabled ? '菜品已恢复上架' : '菜品已下架', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: '更新失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ savingStatus: false });
    }
  },
  updateInventoryDraft(event) {
    const { field } = event.currentTarget.dataset;
    this.setData({ inventoryDraft: { ...this.data.inventoryDraft, [field]: event.detail.value } });
  },
  async saveInventory() {
    const dailyStock = Number(this.data.inventoryDraft.dailyStock);
    const stock = Number(this.data.inventoryDraft.stock);
    if (!Number.isInteger(dailyStock) || !Number.isInteger(stock) || dailyStock < 0 || stock < 0 || stock > dailyStock) {
      wx.showToast({ title: '库存需为非负整数，且剩余不超过每日份数', icon: 'none' });
      return;
    }
    this.setData({ savingInventory: true });
    try {
      const result = await this.callAdmin('updateDishInventory', { id: this.data.id, dailyStock, stock });
      if (!result.ok) throw new Error(result.message || '保存失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({
        dish: { ...this.data.dish, dailyStock: result.dailyStock, stock: result.stock },
        inventoryDraft: { dailyStock: String(result.dailyStock), stock: String(result.stock) },
      });
      wx.showToast({ title: '库存已保存', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: '保存失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ savingInventory: false });
    }
  },
  async toggleManualSoldOut() {
    const manualSoldOut = this.data.dish.manualSoldOut !== true;
    this.setData({ savingStatus: true });
    try {
      const result = await this.callAdmin('updateDishManualSoldOut', { id: this.data.id, manualSoldOut });
      if (!result.ok) throw new Error(result.message || '更新失败');
      getApp().globalData.menuUpdatedAt = Date.now();
      this.setData({ dish: { ...this.data.dish, manualSoldOut: result.manualSoldOut } });
      wx.showToast({ title: result.manualSoldOut ? '菜品已设为售罄' : '菜品已恢复销售', icon: 'success' });
    } catch (error) {
      wx.showToast({ title: '更新失败，请检查权限', icon: 'none' });
    } finally {
      this.setData({ savingStatus: false });
    }
  },
});
