<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app';
import { initCloud } from './services/cloud';
import { ensureLogin } from './services/auth-api';

onLaunch(() => {
  initCloud();

  // 静默登录：wx.login 不需要用户点授权，用户完全无感知。
  // 启动阶段刻意不弹任何错误提示——后端没启动或网络不通时也要能正常进入应用，
  // 真正用到家庭组功能时，那个页面会给出明确的说明和处理办法。
  ensureLogin().catch(() => undefined);
});
</script>

<style>
/*
 * 全局样式只放两件事：设计令牌（CSS 变量）+ 页面级默认值。
 * 具体组件的样式一律写在各自页面的 <style scoped> 里，避免这里变成一锅杂烩。
 *
 * 为什么要用 CSS 变量而不是各页面各写各的十六进制色值？
 *   之前每个页面都直接写 #dc2626、#fee2e2、#450a0a 这些值，一共十几个页面。
 *   结果是同一个"品牌红"在不同页面深浅不一，改一次颜色要全文搜索替换，
 *   而且一定会漏掉几处——页面之间因此看起来"不是一套东西"。
 *   集中成变量之后，改配色只动这一处，全局跟着变。
 *
 * 配色说明（暖陶土 + 清新绿）：
 *   主色是赭红/赤陶（#9A3412），比原先的正红（#dc2626）更沉稳、更"厨房"。
 *   正红在界面上非常抢眼，适合"提醒/促销"，但不适合一个天天要用的家庭工具——
 *   满屏红会让人紧张。换成暖陶土之后，页面的重心回到内容上。
 *   绿色只用在"正向状态"（已加入、保存成功），点缀用，不抢主色。
 */
page {
  /* ---------- 品牌色 ---------- */
  --c-primary: #9a3412; /* 主色：导航栏、主按钮、强调文字 */
  --c-primary-dark: #7c2d12; /* 主色的深一档：按下态 */
  --c-primary-weak: #c2410c; /* 主色的浅一档：次级强调 */
  --c-primary-bg: #fef6f2; /* 主色的极浅底：选中项背景 */

  /* ---------- 语义色 ---------- */
  --c-accent: #059669; /* 正向状态：成功、已完成 */
  --c-accent-bg: #ecfdf5;
  --c-danger: #dc2626; /* 危险动作：删除、解散 */
  --c-danger-bg: #fef2f2;

  /* ---------- 表面与描边 ---------- */
  --c-bg: #fffbeb; /* 页面底：暖白，不是纯白，长时间看不刺眼 */
  --c-surface: #ffffff; /* 卡片面 */
  --c-muted: #f8f2f0; /* 次级背景块（输入框、代码块） */
  --c-border: #f2e6e2; /* 常规描边：能看出边界，又不抢内容 */
  --c-border-strong: #e7d5ce; /* 需要明确分隔时用 */

  /* ---------- 文字 ---------- */
  /* 三档就够了：主文字 / 次要文字 / 极弱提示。
     再多的层级在手机小屏上分不出来，只会让代码更难维护。 */
  --c-text: #1c1917; /* 主文字。在暖白底上对比度约 17:1，远超 4.5:1 的下限 */
  --c-text-2: #78716c; /* 次要文字。对比度约 4.6:1，刚好过线，只用于非关键信息 */
  --c-text-3: #a8a29e; /* 极弱提示。对比度不足，只用于"暂无数据"这类可忽略的文字 */

  /* ---------- 圆角 ---------- */
  --r-sm: 12rpx;
  --r-md: 20rpx;
  --r-lg: 28rpx;
  --r-pill: 999rpx; /* 药丸形：标签、小按钮 */

  /* ---------- 间距（4pt 栅格，全部是 8rpx 的倍数） ---------- */
  --s-1: 8rpx;
  --s-2: 16rpx;
  --s-3: 24rpx;
  --s-4: 32rpx;
  --s-5: 40rpx;
  --s-6: 56rpx;

  /* ---------- 阴影 ---------- */
  /* 卡片阴影非常淡：手机屏幕上重阴影会显脏，轻到"几乎看不见但少了它就没层次"最合适 */
  --shadow-card: 0 2rpx 12rpx rgba(28, 25, 23, 0.04);
  --shadow-float: 0 12rpx 32rpx rgba(154, 52, 18, 0.18);

  /* ---------- 触摸目标 ---------- */
  /* 移动端可点击元素的最小尺寸：44x44 逻辑像素（手指宽度），小程序 rpx 下是 88rpx */
  --touch-min: 88rpx;

  /* ---------- 页面默认值 ---------- */
  min-height: 100%;
  background: #fffbeb;
  color: #1c1917;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  /* 字号不在这里统一设：小程序的字号是用 rpx 按屏幕宽度缩放的，
     写死一个基准值反而会让大屏手机字太小。各页面按需要指定。 */
}

/* 按钮默认样式重置：
   小程序原生 <button> 默认带边框和外边距，直接用在自定义布局里会到处错位。
   统一清掉，需要什么样由各页面自己写。 */
button::after {
  border: none;
}

button {
  margin: 0;
  padding: 0;
  background: transparent;
  line-height: normal;
}

button[disabled] {
  opacity: 0.5;
}
</style>
