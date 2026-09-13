/**
 * 分类的视觉标识：一个底色 + 一个 emoji。
 *
 * 为什么按「分类 ID 取模」来选，而不是按分类名硬编码一张映射表？
 *   分类现在是可以改名、可以增删改的。硬编码「凉菜 → 🥗」这种表的话，
 *   用户把「凉菜」改成「凉拌菜」之后，这个分类下所有菜就找不到图标了。
 *   改成按 ID 取模之后，每个分类都会稳定地分到一个颜色和图标，
 *   不管它叫什么名字；而且同一个分类下的所有菜看起来是一组，扫一眼就能区分。
 *
 * 为什么颜色都很淡？
 *   色块上面要放一个彩色 emoji。底色太深会和 emoji 打架，两个都看不清。
 *   淡底 + 彩色图标是常见的搭配。
 */

/** 底色池：一组低饱和的暖调色，和主色（暖陶土）在同一色系里 */
const COLORS = [
  '#FDF0E7',
  '#F6EBE3',
  '#EFE9E2',
  '#E8EFE9',
  '#E6EEF3',
  '#F1EAF3',
  '#FBE9E7',
  '#EDEDE6',
];

/** 图标池：和"吃"相关的通用图形，不绑定具体分类名 */
const EMOJIS = ['🥗', '🍲', '🥘', '🍜', '🍚', '🍰', '🥤', '🍳', '🥩', '🍤', '🥟', '🍮'];

/**
 * 由分类 ID 算出一个稳定的下标。
 *
 * 不追求"真正的哈希函数"——同一个 ID 每次算出来一样就够了。
 * 后端返回的是数字 ID 的字符串形式，直接取数值再取模。
 */
function indexFromId(categoryId: string, length: number): number {
  const value = Number(categoryId);
  if (!Number.isFinite(value)) return 0;
  return Math.abs(Math.trunc(value)) % length;
}

/** 取分类对应的底色（十六进制字符串，可直接绑定到 style） */
export function categoryColor(categoryId: string): string {
  return COLORS[indexFromId(categoryId, COLORS.length)];
}

/** 取分类对应的 emoji */
export function categoryEmoji(categoryId: string): string {
  return EMOJIS[indexFromId(categoryId, EMOJIS.length)];
}
