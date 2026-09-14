/** 金额格式化：统一保留两位小数，非法值按 0 处理 */
export function formatMoney(value: number | string | null | undefined): string {
  const amount = Number(value || 0);
  return amount.toFixed(2);
}

/**
 * 轻提示：统一走 none 图标，避免报错弹窗遮挡内容。
 *
 * 参数设计成 unknown 而不是 string，是故意的：
 * 调用方经常直接传 catch 到的 error（一个 Error 对象），
 * 如果这里只收 string，Error 对象会被原样塞进 showToast 的 title，
 * 触发微信报错：showToast:fail parameter error: parameter.title should be String。
 * 所以在这里统一转成字符串，而不是要求每个调用点自己写一遍判断。
 */
export function showError(error: unknown): void {
  let message: string;
  if (error instanceof Error) {
    message = error.message;
  } else if (typeof error === 'string') {
    message = error;
  } else {
    message = '操作失败';
  }
  uni.showToast({ title: message || '操作失败', icon: 'none' });
}
