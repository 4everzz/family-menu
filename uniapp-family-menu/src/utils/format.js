export function formatMoney(value) {
  const amount = Number(value || 0);
  return amount.toFixed(2);
}

export function showError(message) {
  uni.showToast({ title: message || '操作失败', icon: 'none' });
}
