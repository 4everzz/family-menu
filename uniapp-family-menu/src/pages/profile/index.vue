<template>
  <view class="profile-page">
    <!--
      菜单管理：只有创建人能改菜单（后端也会拦，这里隐藏只是体验），
      所以普通成员整块不显示，换成一句说明——否则他会点进去、填完表单才被拒绝，
      那是最难查的一种体验问题。
    -->
    <view v-if="isOwner" class="group">
      <text class="group-title">菜单管理</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goCategoryManage">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-clay)' }">
            <image class="entry-icon-img" src="/static/icons/tags.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">分类管理</text>
            <text class="entry-desc">增删改你们家的菜谱分类</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>

        <view class="entry-item" hover-class="tap" @click="goRecipeManage">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-sand)' }">
            <image class="entry-icon-img" src="/static/icons/form.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">菜品管理</text>
            <text class="entry-desc">添加、修改、删除菜谱</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <view v-else class="group">
      <view class="entry-group">
        <view class="entry-item">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-stone)' }">
            <image class="entry-icon-img" src="/static/icons/lock.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">菜谱由创建人维护</text>
            <text class="entry-desc">你可以随时翻阅；要改内容可以提醒一下创建人</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 其他家庭功能 -->
    <view class="group">
      <text class="group-title">其他</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goFridge">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-sage)' }">
            <image class="entry-icon-img" src="/static/icons/container.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">家庭冰箱</text>
            <text class="entry-desc">看看家里现在有什么菜</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 设置：切换账号、切换家庭这类"配置类"动作统一收在这里，不散落在各页面 -->
    <view class="group">
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goSettings">
          <view class="entry-icon" :style="{ background: 'var(--c-tint-stone)' }">
            <image class="entry-icon-img" src="/static/icons/setting.png" mode="aspectFit" />
          </view>
          <view class="entry-main">
            <text class="entry-name">设置</text>
            <text class="entry-desc">切换账号、切换家庭</text>
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
 * 三个改动值得说明：
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
 *
 * 3. 摘掉了原本页面顶部那张「当前家庭 / 切换」卡片，改为一个「设置」入口。
 *    原因是切换家庭会影响菜谱、冰箱这些家庭共享数据——它属于"配置类"动作，
 *    不该和日常浏览混在同一个手势里。所有这类动作（切换账号、切换家庭）
 *    统一收进设置页，其余页面只负责显示、不提供切换。
 *
 * 4. 「菜单管理」只对**创建人**显示。
 *    创建人有三项专属权力：改菜单、解散家庭组、移除成员。
 *    普通成员看到的是"菜谱由创建人维护"的说明卡片——
 *    这比"让他点进去、填完表单才被拒绝"要好得多。
 *    隐藏只是体验，真正的拦截在后端（SpaceService.ensure_owner）。
 */

import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { getCurrentSpace, resolveCurrentSpace } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';

/**
 * 我是不是这个家的创建人。
 *
 * 只有创建人能改菜单，所以「菜单管理」入口按这个值显示/隐藏。
 * 注意这**只是体验**：后端每个写接口都会再校验一次，
 * 别人绕开界面直接调接口一样会被 403 拦住。
 */
const isOwner = ref(false);

async function refreshRole(): Promise<void> {
  // 先用本地缓存里的角色立刻定下来，页面不会闪一下再变
  isOwner.value = getCurrentSpace()?.myRole === 'admin';

  // 还没登录过就不主动请求，避免每次进「我的」都触发一次登录
  if (!hasValidToken()) return;

  try {
    await resolveCurrentSpace();
    isOwner.value = getCurrentSpace()?.myRole === 'admin';
  } catch (error) {
    // 拉取失败（例如后端没启动）时沿用缓存里的判断，不打断页面浏览
  }
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

/** 设置页：切换账号、切换家庭都在里面 */
function goSettings() {
  uni.navigateTo({ url: '/pages/settings/index' });
}

onShow(refreshRole);
</script>

<style scoped>
.profile-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
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
  line-height: 1;
}
/* 图标用 SVG 而不是 emoji：emoji 依赖手机字体，同一台手机不同系统版本长得都不一样，
   也没法用设计令牌控制颜色；SVG 是矢量，随设计系统走，缩放不糊 */
.entry-icon-img { width: 44rpx; height: 44rpx; }
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
