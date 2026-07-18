async function callAdmin(action, payload = {}) {
  const response = await wx.cloud.callFunction({
    name: 'admin-menu',
    data: { action, ...payload },
  });
  return response.result || {};
}

async function loadAdminOrders() {
  const result = await callAdmin('listAdminOrders');
  if (!result.ok) throw new Error(result.message || '读取订单失败');
  return result.orders || [];
}

async function loadAdminOrder(id) {
  const orders = await loadAdminOrders();
  return orders.find((item) => item.id === id) || null;
}

module.exports = { callAdmin, loadAdminOrder, loadAdminOrders };
