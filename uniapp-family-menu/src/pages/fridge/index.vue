<template>
  <view class="fridge-page">
    <view class="space-bar">
      <view class="space-main">
        <text class="space-label">当前家庭</text>
        <text class="space-name">{{ spaceName || '未加入家庭组' }}</text>
      </view>
    </view>

    <view class="state-card">
      <view class="state-icon">🧊</view>
      <text class="state-title">家庭冰箱正在施工</text>
      <text class="state-copy">接入后可以记录家里现在有哪些食材，用来挑选今天做什么菜。</text>
      <view class="state-note">
        <text class="state-note-text">第一版为轻量清单：只记录「有 / 没有」，不记数量和保质期。</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { getCurrentSpaceName } from '../../utils/space-context';

// 冰箱属于当前家庭组：在「我的」页面切换家庭后，这里显示的家庭会同步变化
const spaceName = ref('');

onShow(() => {
  spaceName.value = getCurrentSpaceName();
});
</script>

<style scoped>
.fridge-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.space-bar {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  min-height: 120rpx;
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.space-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: var(--s-1); }
.space-label { color: var(--c-text-2); font-size: 23rpx; }
.space-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 32rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-5) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  text-align: center;
}
/* 大图标块：占位页需要一点视觉重量，否则整页看起来像加载失败 */
.state-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 140rpx;
  height: 140rpx;
  border-radius: var(--r-lg);
  background: #e8efe9;
  font-size: 64rpx;
  line-height: 1;
}
.state-title { color: var(--c-text); font-size: 34rpx; font-weight: 500; }
.state-copy { color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; }
.state-note {
  width: 100%;
  margin-top: var(--s-1);
  padding: var(--s-3);
  border-radius: var(--r-md);
  background: var(--c-primary-bg);
  box-sizing: border-box;
}
.state-note-text { display: block; color: var(--c-primary-dark); font-size: 23rpx; line-height: 1.7; text-align: left; }
</style>
