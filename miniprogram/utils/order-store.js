const { callAdminMenu } = require('./shop-context');
const { getCurrentShop } = require('./shop-store');
const { clearRuntimeCache, loadRuntimeCache } = require('./runtime-cache');

const MY_ORDERS_CACHE_TTL = 15 * 1000;

function getMyOrdersCacheKey() {
  const shop = getCurrentShop();
  return `my-orders:${shop && shop.id || ''}:${shop && shop.tableId || ''}:${shop && shop.entryToken || ''}`;
}

function toDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  if (typeof value === 'number' || typeof value === 'string') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (value && typeof value === 'object') {
    if (value.$date) return toDate(value.$date);
    if (Number.isFinite(value._seconds)) return new Date(value._seconds * 1000);
    if (Number.isFinite(value.seconds)) return new Date(value.seconds * 1000);
  }
  return null;
}

function padNumber(value) {
  return String(value).padStart(2, '0');
}

function formatChinaDateTime(value, fallback) {
  const date = toDate(value);
  if (!date) return fallback || '';

  // 真机上部分基础库不支持 Intl，这里手动按北京时间格式化。
  const chinaOffsetMs = 8 * 60 * 60 * 1000;
  const chinaDate = new Date(date.getTime() + chinaOffsetMs);

  const year = chinaDate.getUTCFullYear();
  const month = padNumber(chinaDate.getUTCMonth() + 1);
  const day = padNumber(chinaDate.getUTCDate());
  const hour = padNumber(chinaDate.getUTCHours());
  const minute = padNumber(chinaDate.getUTCMinutes());
  const second = padNumber(chinaDate.getUTCSeconds());

  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

function normalizeOrder(order) {
  const items = (order.items || []).map((item) => ({
    ...item,
    cartKey: item.cartKey || `${item.id}|${(item.options || []).join('|')}`,
    optionsText: item.optionsText || (item.options || []).join('、'),
  }));

  return {
    ...order,
    items,
    summary: order.summary || items.map((item) => `${item.name} × ${item.quantity}`).join('、'),
    createdAt: formatChinaDateTime(order.createdAtServer, order.createdAt),
  };
}

async function callOrderApi(action, payload = {}) {
  return callAdminMenu(action, payload);
}

async function loadMyOrders(options = {}) {
  const result = await loadRuntimeCache(getMyOrdersCacheKey(), MY_ORDERS_CACHE_TTL, async () => {
    const response = await callOrderApi('listMyOrders');
    if (!response.ok) throw new Error(response.message || '读取订单失败');
    return (response.orders || []).map(normalizeOrder);
  }, options && options.force === true);
  return Array.isArray(result) ? result : [];
}

async function loadMyOrder(id) {
  const result = await callOrderApi('getMyOrder', { id });
  if (!result.ok || !result.order) throw new Error(result.message || '读取订单失败');
  return normalizeOrder(result.order);
}

function invalidateMyOrders() {
  clearRuntimeCache(getMyOrdersCacheKey());
}

module.exports = { loadMyOrders, loadMyOrder, invalidateMyOrders, formatChinaDateTime };
