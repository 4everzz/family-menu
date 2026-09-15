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

/** 两位数字，用于拼时间 */
function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

/** 两个时间是不是同一天 */
function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * 把后端返回的时间转成"人话"。
 *
 * 输出规则（按信息量从高到低，越近的时间说得越细）：
 *   今天   → 「今天 12:30」
 *   昨天   → 「昨天 12:30」
 *   今年内 → 「9月12日 12:30」
 *   跨年   → 「2025年9月12日」
 *
 * ⚠️ 为什么先做一次"补时区"的处理？
 *   后端存的是带时区的 UTC 时间。如果某个接口返回的字符串少了时区后缀
 *   （例如 "2026-09-15T02:30:00"），JS 的 new Date() 会**按本机时区**解析它，
 *   于是比"今天 10:30 点的单"显示的却是 02:30 —— 差了整整 8 小时，
 *   而且只在北京时区以外的机器上才发现得了。
 *   所以这里先看字符串有没有时区信息，没有就补一个 Z 再解析。
 */
export function formatDateTime(value: string): string {
  if (!value) return '';

  // 已经带 Z 或 +08:00 / +0800 的，原样交给 Date；没带的按 UTC 处理
  const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return '';

  const now = new Date();
  const hhmm = `${pad(date.getHours())}:${pad(date.getMinutes())}`;

  if (isSameDay(date, now)) return `今天 ${hhmm}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (isSameDay(date, yesterday)) return `昨天 ${hhmm}`;

  if (date.getFullYear() === now.getFullYear()) {
    return `${date.getMonth() + 1}月${date.getDate()}日 ${hhmm}`;
  }
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}
