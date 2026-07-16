const ROLES = {
  GUEST: 'guest',
  USER: 'user',
  MANAGER: 'manager',
};

const ORDER_STATUS = {
  SUBMITTED: 'submitted',
  COOKING: 'cooking',
  SERVING: 'serving',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
};

const COLLECTIONS = {
  USERS: 'users',
  CATEGORIES: 'categories',
  DISHES: 'dishes',
  ORDERS: 'orders',
};

const ORDER_STATUS_LABELS = {
  [ORDER_STATUS.SUBMITTED]: '已提交',
  [ORDER_STATUS.COOKING]: '制作中',
  [ORDER_STATUS.SERVING]: '待上菜',
  [ORDER_STATUS.COMPLETED]: '已完成',
  [ORDER_STATUS.CANCELLED]: '已取消',
};

module.exports = {
  ROLES,
  ORDER_STATUS,
  ORDER_STATUS_LABELS,
  COLLECTIONS,
};
