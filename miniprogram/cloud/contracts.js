// 云开发集合与业务状态约定，供后续新增页面或云函数时统一参考。
const ROLES = {
  USER: 'user',
  MANAGER: 'manager',
  SUPER_ADMIN: 'super_admin',
};

const ORDER_STATUS = {
  COOKING: '制作中',
  COMPLETED: '已完成',
};

const COLLECTIONS = {
  USERS: 'users',
  CATEGORIES: 'categories',
  DISHES: 'dishes',
  ORDERS: 'orders',
};

module.exports = {
  ROLES,
  ORDER_STATUS,
  COLLECTIONS,
};
