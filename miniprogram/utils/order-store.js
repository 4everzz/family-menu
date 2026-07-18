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

module.exports = { loadMyOrders, loadMyOrder };
