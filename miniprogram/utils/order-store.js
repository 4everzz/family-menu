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

function formatChinaDateTime(value, fallback) {
  const date = toDate(value);
  if (!date) return fallback || '';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
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
  const response = await wx.cloud.callFunction({
    name: 'admin-menu',
    data: { action, ...payload },
  });
  return response.result || {};
}

async function loadMyOrders() {
  const result = await callOrderApi('listMyOrders');
  if (!result.ok) throw new Error(result.message || '读取订单失败');
  return (result.orders || []).map(normalizeOrder);
}

async function loadMyOrder(id) {
  const result = await callOrderApi('getMyOrder', { id });
  if (!result.ok || !result.order) throw new Error(result.message || '读取订单失败');
  return normalizeOrder(result.order);
}

module.exports = { loadMyOrders, loadMyOrder, formatChinaDateTime };
