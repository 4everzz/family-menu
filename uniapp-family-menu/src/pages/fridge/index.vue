<template>
  <view class="fridge-page">
    <view class="space-bar">
      <text class="space-label">当前家庭</text>
      <text class="space-name">{{ spaceName || '未加入家庭组' }}</text>
    </view>

    <view class="state-card">
      <text class="state-title">家庭冰箱正在施工</text>
      <text class="state-copy">接入后可以记录家里现在有哪些食材，用来挑选今天做什么菜。</text>
      <text class="state-note">第一版为轻量清单：只记录「有 / 没有」，不记数量和保质期。</text>
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
.fridge-page { min-height: 100vh; padding: 28rpx 24rpx calc(48rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.space-bar { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; padding: 24rpx 26rpx; border: 2rpx solid #fee2e2; border-radius: 20rpx; background: #fff; }
.space-label { color: #78716c; font-size: 24rpx; }
.space-name { color: #450a0a; font-size: 28rpx; font-weight: 700; }
.state-card { display: flex; flex-direction: column; align-items: center; gap: 16rpx; margin-top: 40rpx; padding: 48rpx 32rpx; border: 2rpx solid #fee2e2; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 20rpx rgba(69, 10, 10, .05); text-align: center; }
.state-title { color: #450a0a; font-size: 34rpx; font-weight: 800; }
.state-copy { color: #78716c; font-size: 25rpx; line-height: 1.6; }
.state-note { margin-top: 8rpx; padding: 16rpx 20rpx; border-radius: 14rpx; background: #fff7ed; color: #7c2d12; font-size: 23rpx; line-height: 1.6; text-align: left; }
</style>
