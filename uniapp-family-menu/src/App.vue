<script setup lang="ts">
/**
 * App 入口。
 *
 * ⚠️ 这里**刻意不做**启动登录（改造前这里有一句静默登录，已删除）。
 *    原因：启动阶段页面栈还没建立，此时调 navigateTo 跳登录页，各端表现不一致。
 *    改由**需要数据的页面**在取数前调 ensureLogin() 来引导登录（见 services/auth-api.ts）：
 *    页面已经在了，跳转可靠，也不会出现"App 刚打开就被弹去登录页"的突兀感。
 *
 * ⚠️ 这个 script 块本身不能删：Vue 的单文件组件要求至少有 <template> 或 <script> 之一，
 *    只剩 <style> 会直接编译失败（At least one <template> or <script> is required）。
 *    删启动逻辑时如果连整块一起删掉，就会踩这个坑。
 */

import { onLaunch } from '@dcloudio/uni-app';
import { setCurrentSpace } from './utils/space-context';
import { hasValidToken } from './utils/token';

onLaunch(() => {
  // 本机没有有效令牌时，顺手清掉残留的"当前家庭"缓存。
  // 不清的话，「设置」页会先用缓存里的家庭名把界面填上、昵称却显示"未登录"，
  // 看起来像登到了别人家里。
  if (!hasValidToken()) {
    setCurrentSpace(null);
  }
});
</script>

<style>
/*
 * 全局样式只放两件事：设计令牌（CSS 变量）+ 页面级默认值。
 * 具体组件的样式一律写在各自页面的 <style scoped> 里，避免这里变成一锅杂烩。
 *
 * 启动逻辑在文件顶部的 <script setup> 里，不在这里。
 *
 * 为什么下面的配色要用 CSS 变量而不是各页面各写各的十六进制色值？
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
  --c-primary-border: #f0d9cd; /* 主色的浅描边：提醒卡片边界 */

  /* ---------- 语义色 ---------- */
  --c-accent: #059669; /* 正向状态：成功、已完成 */
  --c-accent-bg: #ecfdf5;
  --c-danger: #dc2626; /* 危险动作：删除、解散 */
  --c-danger-bg: #fef2f2;
  --c-danger-text: #b91c1c; /* 危险文字：删除按钮、已过期标签（配 --c-danger-bg 底） */
  --c-warn: #d97706; /* 提醒色：临期（还没过期，但快了） */
  --c-warn-bg: #fff8eb; /* 提醒浅底 */
  --c-warn-text: #b45309; /* 提醒文字（配 --c-warn-bg 底） */

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

  /* ---------- 语义浅底（图标方块用） ---------- */
  /* 这几个是"浅到几乎看不出颜色"的底，专门垫图标。
     为什么不让各页面自己写十六进制？同一块"分类底色"三个页面各写一次，
     改的时候一定漏一处——「我的」页之前就是 4 块互不相干的硬编码色值。 */
  --c-tint-clay: #fdf0e7; /* 暖陶土：分类、菜谱内容 */
  --c-tint-sand: #f6ebe3; /* 暖沙：编辑、录入 */
  --c-tint-stone: #efeae6; /* 中性：设置、受限 */
  --c-tint-sage: #e8efe9; /* 灰绿：冰箱、库存 */
  --c-sage-text: #4d7c0f; /* 灰绿文字：冰箱分类/存放标签（配 --c-tint-sage 底） */

  /* ---------- 状态色 ---------- */
  --c-danger-border: #f7c1c1; /* 错误卡片描边：比 --c-danger 浅得多，只用于边界 */
  --c-warn-border: #f3d29a; /* 提醒卡片描边：比 --c-warn 浅得多，只用于边界 */
  --c-disabled: #ddc4b8; /* 主按钮的禁用态底色 */

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

/* ---------- 全局按压反馈 ---------- */
/*
  移动端"点下去必须有反应"。这一条在 UX 清单里是 CRITICAL 级：
  没有反馈，用户会怀疑自己没点中，然后重复点——在删除、解散这类操作上尤其危险。

  用法：<view hover-class="tap" ...>。小程序里按下会**附加**这个类，
  用透明度而不是改背景色，是因为背景色会被页面自己的 `.xxx { background }` 盖掉
  （app.wxss 在 page.wxss 之前加载，同权重下页面样式赢）。
  透明度几乎没人会给卡片单独设，所以不会被覆盖，也不会改变布局尺寸。
*/
.tap { opacity: 0.72; }
</style>
