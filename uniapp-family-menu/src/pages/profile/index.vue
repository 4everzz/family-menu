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

    <!-- 菜单管理：改菜谱的地方，和菜单页（只读浏览）分开 -->
    <view class="group">
      <text class="group-title">菜单管理</text>
      <view class="entry-group">
        <view class="entry-item" @click="goCategoryManage">
          <view class="entry-icon" :style="{ background: '#FDF0E7' }">🗂️</view>
          <view class="entry-main">
            <text class="entry-name">分类管理</text>
            <text class="entry-desc">增删改你们家的菜谱分类</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item" @click="goRecipeManage">
          <view class="entry-icon" :style="{ background: '#F6EBE3' }">📝</view>
          <view class="entry-main">
            <text class="entry-name">菜品管理</text>
            <text class="entry-desc">添加、修改、删除菜谱</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 其他家庭功能 -->
    <view class="group">
      <text class="group-title">其他</text>
      <view class="entry-group">
        <view class="entry-item" @click="goFridge">
          <view class="entry-icon" :style="{ background: '#E8EFE9' }">🧊</view>
          <view class="entry-main">
            <text class="entry-name">家庭冰箱</text>
            <text class="entry-desc">看看家里现在有什么菜</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <text class="page-note">个人资料与成员管理将在后续模块接入</text>
  </view>
</template>

<script setup lang="ts">
/**
 * 「我的」页。
 *
 * 两个改动值得说明：
 *
 * 1. 摘掉了「我的订单」入口（页面代码仍然保留在 pages/orders 里，只是没有入口）。
 *    那个页面是旧商家版的遗留：它的逻辑是"先扫码进店，再看你在那家店的订单"。
 *    在家庭场景里根本没有"订单"这个东西——家里做饭不需要下单，
 *    所以用户点进去只会撞上"请先进入店铺"这种莫名其妙的提示。
 *    留着入口比没有入口更糟，先摘掉。
 *
 * 2. 加了「菜单管理」分组（分类管理 + 菜品管理）。
 *    菜单页现在是纯浏览，改菜谱统一收在这里。
 *    浏览和编辑分开，是为了避免翻菜谱时手滑进表单、甚至误删。
 */

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

/** 分类管理：增删改这个家的菜谱分类 */
function goCategoryManage() {
  uni.navigateTo({ url: '/pages/manage/category' });
}

/** 菜品管理：增删改菜谱 */
function goRecipeManage() {
  uni.navigateTo({ url: '/pages/manage/recipe' });
}

/** 家庭冰箱：家庭共享功能，按当前家庭组展示 */
function goFridge() {
  uni.navigateTo({ url: '/pages/fridge/index' });
}

onShow(refresh);
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.space-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.space-action {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: 64rpx;
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: 25rpx;
}

/* 分组标题：把"设置类"和"功能类"分开，条目一多也不至于糊成一片 */
.group { margin-top: var(--s-4); }
.group-title {
  display: block;
  margin: 0 var(--s-1) var(--s-2);
  color: var(--c-text-2);
  font-size: 23rpx;
}

.entry-group {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.entry-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 136rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.entry-item:last-child { border-bottom: none; }
/* 左侧一个小色块图标：比纯文字条目更容易扫读，也比塞一张图片轻 */
.entry-icon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80rpx;
  height: 80rpx;
  border-radius: var(--r-sm);
  font-size: 38rpx;
  line-height: 1;
}
.entry-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.entry-name { color: var(--c-text); font-size: 29rpx; font-weight: 500; }
.entry-desc {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 23rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 40rpx; line-height: 1; }

.page-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
