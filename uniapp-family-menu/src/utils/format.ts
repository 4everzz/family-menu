/** 金额格式化：统一保留两位小数，非法值按 0 处理 */
export function formatMoney(value: number | string | null | undefined): string {
  const amount = Number(value || 0);
  return amount.toFixed(2);
}

/** 轻提示：统一走 none 图标，避免报错弹窗遮挡内容 */
export function showError(message?: string): void {
  uni.showToast({ title: message || '操作失败', icon: 'none' });
}
