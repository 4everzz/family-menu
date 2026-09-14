/**
 * 主题常量（**给 JS 用**的那一份）。
 *
 * 为什么 CSS 变量不够？
 *   CSS 变量只在样式里生效。像 `uni.showModal({ confirmColor })` 这种
 *   写在 JS 里的颜色，拿不到 `var(--c-primary)`——微信只认一个真实的色值字符串。
 *   之前就是因为没有这个东西，各页面的确认弹窗各写各的：
 *   三个用旧的正红 #dc2626、三个用暖陶土 #9a3412、一个用深红 #b91c1c，
 *   同一个产品里弹窗按钮有三种红，肉眼一看就不像一套东西。
 *
 * ⚠️ 改配色时要同时改两处，值必须一致：
 *   - `src/App.vue` 的 `--c-primary` / `--c-danger`
 *   - 本文件
 */

/** 品牌主色，对应 App.vue 的 `--c-primary`。用于普通确认按钮 */
export const PRIMARY = '#9a3412';

/** 危险色，对应 App.vue 的 `--c-danger`。用于删除、解散这类不可逆操作 */
export const DANGER = '#dc2626';
