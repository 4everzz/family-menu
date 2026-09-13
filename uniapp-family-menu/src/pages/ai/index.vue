<template>
  <view class="ai-page">
    <view class="hero">
      <view class="hero-badge">施工中</view>
      <text class="hero-title">AI 助手</text>
      <text class="hero-copy">这里将用对话的方式帮你决定今天吃什么。</text>
    </view>

    <view class="plan-card">
      <text class="plan-title">计划支持</text>
      <view v-for="item in plans" :key="item" class="plan-row">
        <view class="plan-dot" />
        <text class="plan-text">{{ item }}</text>
      </view>
    </view>

    <text class="page-note">功能开发中，敬请期待</text>
  </view>
</template>

<script setup>
// AI 页面占位。
// 等后端 FastAPI 与模型接口接通后，把这里替换为真实的对话界面。
// 说明：接入简单对话并不需要 LangChain，后端一次 HTTP 请求即可；
// LangChain 与 LangGraph 会在「文档问答」和「多步推荐 Agent」阶段引入。

const plans = [
  '按家庭冰箱里现有的食材，推荐能做什么菜',
  '按减脂期、低糖、忌口等条件筛选菜品',
  '按人数、口味和预算搭配一桌菜',
];
</script>

<style scoped>
.ai-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

/* 头部保留品牌感：这是三个 tab 里唯一"还没有内容"的页面，
   用一块有存在感的头部撑住，比直接摆一张空卡片显得不那么像坏掉了 */
.hero {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--s-2);
  padding: var(--s-5) var(--s-3);
  border-radius: var(--r-lg);
  background: var(--c-primary-bg);
  border: 2rpx solid var(--c-border);
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  height: 48rpx;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 22rpx;
}
.hero-title { color: var(--c-text); font-size: 44rpx; font-weight: 500; }
.hero-copy { color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; }

.plan-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-3);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.plan-title { color: var(--c-text-2); font-size: 23rpx; }
.plan-row { display: flex; align-items: flex-start; gap: var(--s-2); }
/* 用一个小圆点做项目符号，比文字里的「·」对齐更稳，换行时也不会缩进错位 */
.plan-dot {
  flex: 0 0 auto;
  width: 12rpx;
  height: 12rpx;
  margin-top: 14rpx;
  border-radius: 50%;
  background: var(--c-primary);
}
.plan-text { min-width: 0; flex: 1; color: var(--c-text); font-size: 26rpx; line-height: 1.7; }

.page-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
