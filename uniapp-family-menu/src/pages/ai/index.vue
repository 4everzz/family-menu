<template>
  <view class="ai-page">
    <view class="state-card">
      <text class="state-title">AI 助手正在施工</text>
      <text class="state-copy">这里将用对话的方式帮你决定今天吃什么。</text>

      <view class="plan-list">
        <text class="plan-item">按家庭冰箱里现有的食材，推荐能做什么菜</text>
        <text class="plan-item">按减脂期、低糖、忌口等条件筛选菜品</text>
        <text class="plan-item">按人数、口味和预算搭配一桌菜</text>
      </view>

      <text class="state-note">功能开发中，敬请期待</text>
    </view>
  </view>
</template>

<script setup>
// AI 页面占位。
// 等后端 FastAPI 与模型接口接通后，把这里替换为真实的对话界面。
// 说明：接入简单对话并不需要 LangChain，后端一次 HTTP 请求即可；
// LangChain 与 LangGraph 会在「文档问答」和「多步推荐 Agent」阶段引入。
</script>

<style scoped>
.ai-page { min-height: 100vh; padding: 28rpx 24rpx calc(48rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.state-card { display: flex; flex-direction: column; align-items: center; gap: 14rpx; margin-top: 120rpx; padding: 48rpx 32rpx; border: 2rpx solid #fee2e2; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 20rpx rgba(69, 10, 10, .05); text-align: center; }
.state-title { color: #450a0a; font-size: 34rpx; font-weight: 800; }
.state-copy { color: #78716c; font-size: 25rpx; line-height: 1.6; }
.plan-list { width: 100%; margin-top: 16rpx; padding: 22rpx 24rpx; border-radius: 16rpx; background: #fff7ed; box-sizing: border-box; }
.plan-item { display: block; color: #7c2d12; font-size: 24rpx; line-height: 1.9; text-align: left; }
.state-note { margin-top: 20rpx; color: #a8a29e; font-size: 23rpx; }
</style>
