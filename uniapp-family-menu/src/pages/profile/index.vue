<template>
  <view class="profile-page">
    <!-- 当前家庭组：切换后冰箱等家庭数据都会跟随当前家庭变化 -->
    <view class="space-card" @click="onSwitchSpace">
      <view class="space-main">
        <text class="space-label">当前家庭</text>
        <text class="space-name">{{ spaceName || '未加入家庭组' }}</text>
      </view>
      <text class="space-action">切换</text>
    </view>

    <!-- 功能入口 -->
    <view class="entry-group">
      <view class="entry-item" @click="goFridge">
        <view class="entry-main">
          <text class="entry-name">家庭冰箱</text>
          <text class="entry-desc">看看家里现在有什么菜</text>
        </view>
        <text class="entry-arrow">›</text>
      </view>

      <view class="entry-item" @click="goOrders">
        <view class="entry-main">
          <text class="entry-name">我的订单</text>
          <text class="entry-desc">查看历史下单记录</text>
        </view>
        <text class="entry-arrow">›</text>
      </view>
    </view>

    <text class="page-note">个人资料与家庭组管理将在后续模块接入</text>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { getCurrentSpaceName, resolveCurrentSpace } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';

const spaceName = ref('');

/**
 * 刷新页面上显示的家庭组名称。
 *
 * 先用本地缓存立刻显示（页面不会空着），再去后端拉一次最新列表并校正：
 * 万一"当前家庭"已经失效（比如被移出），这里会自动切到另一个可用的家庭组。
 */
async function refresh() {
  spaceName.value = getCurrentSpaceName();

  // 还没登录过就不主动请求，避免每次进「我的」都触发一次登录
  if (!hasValidToken()) return;

  try {
    await resolveCurrentSpace();
    spaceName.value = getCurrentSpaceName();
  } catch (error) {
    // 拉取失败（例如后端没启动）时保留缓存里的名字，不打断页面浏览
  }
}

/** 进入家庭组页面：在那里切换、创建、加入 */
function onSwitchSpace() {
  uni.navigateTo({ url: '/pages/space/index' });
}

/** 家庭冰箱：家庭共享功能，按当前家庭组展示 */
function goFridge() {
  uni.navigateTo({ url: '/pages/fridge/index' });
}

/** 我的订单：已从底部导航移入本页，属于普通页面跳转（不能用 switchTab） */
function goOrders() {
  uni.navigateTo({ url: '/pages/orders/index' });
}

onShow(refresh);
</script>

<style scoped>
.profile-page { min-height: 100vh; padding: 28rpx 24rpx calc(48rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.space-card { display: flex; align-items: center; justify-content: space-between; gap: 20rpx; padding: 30rpx 26rpx; border: 2rpx solid #fecaca; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 20rpx rgba(69, 10, 10, .05); }
.space-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 10rpx; }
.space-label { color: #78716c; font-size: 23rpx; }
.space-name { color: #450a0a; font-size: 32rpx; font-weight: 800; }
.space-action { flex: 0 0 auto; padding: 12rpx 22rpx; border: 2rpx solid #fecaca; border-radius: 999rpx; background: #fff7ed; color: #b91c1c; font-size: 25rpx; font-weight: 700; }
.entry-group { display: flex; flex-direction: column; gap: 18rpx; margin-top: 28rpx; }
.entry-item { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; padding: 26rpx; border: 2rpx solid #fee2e2; border-radius: 20rpx; background: #fff; box-shadow: 0 8rpx 18rpx rgba(69, 10, 10, .04); }
.entry-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 8rpx; }
.entry-name { color: #450a0a; font-size: 29rpx; font-weight: 700; }
.entry-desc { color: #78716c; font-size: 23rpx; }
.entry-arrow { flex: 0 0 auto; color: #d6d3d1; font-size: 40rpx; line-height: 1; }
.page-note { display: block; margin-top: 34rpx; color: #a8a29e; font-size: 22rpx; text-align: center; }
</style>
