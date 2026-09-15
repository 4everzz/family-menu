<template>
  <view class="alerts-page">
    <!-- 当前家庭组：在「我的 → 设置 → 切换家庭」里换家后，这里会同步变化 -->
    <view class="space-bar">
      <view class="space-main">
        <text class="space-label">当前家庭</text>
        <text class="space-name">{{ spaceName || '未加入家庭组' }}</text>
      </view>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <template v-else>
      <!-- 没选家庭组：提醒依附于家庭共享域，没有家就无从算 -->
      <view v-if="!hasSpace" class="empty">
        <text class="empty-text">还没有选择家庭组</text>
        <text class="empty-hint">去「我的 → 设置 → 切换家庭」选一个家</text>
      </view>

      <template v-else>
        <!-- 按类别筛选：已过期 / 临期 / 缺货，纯前端过滤（后端已把全部提醒一次返回） -->
        <view v-if="alerts.length" class="filters">
          <view class="filter-scroll">
            <view class="filter-track">
              <view
                v-for="f in filters"
                :key="f"
                class="chip"
                :class="{ active: activeFilter === f }"
                hover-class="tap"
                @click="activeFilter = f"
              >{{ f }}</view>
            </view>
          </view>
        </view>

        <!-- 列表：按当前筛选展示 -->
        <view v-if="filtered.length" class="list">
          <view
            v-for="a in filtered"
            :key="a.id"
            class="card"
            :class="a.level"
            hover-class="tap"
            @click="openAlert(a)"
          >
            <view class="card-icon" :class="a.level" aria-label="提醒"></view>
            <view class="card-main">
              <view class="card-head">
                <text class="card-title">{{ a.title }}</text>
                <text class="card-badge" :class="a.level">{{ badge(a) }}</text>
              </view>
              <text v-if="a.detail" class="card-detail">{{ a.detail }}</text>
            </view>
            <text class="card-arrow">›</text>
          </view>
        </view>

        <!-- 有数据，但当前筛选项没有命中 -->
        <view v-else-if="alerts.length" class="empty">
          <text class="empty-text">这个分类下暂时没有提醒</text>
          <text class="empty-hint">换个筛选条件看看</text>
        </view>

        <!-- 有家庭组，但暂时没有要提醒的事 -->
        <view v-else class="empty">
          <text class="empty-text">暂时没有需要提醒的事</text>
          <text class="empty-hint">冰箱食材都还新鲜、库存充足</text>
        </view>
      </template>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 家庭提醒列表页。
 *
 * 三个要点：
 * 1. 提醒是"派生数据"，后端每次实时算，前端不存任何"已读/忽略"状态——
 *    冰箱状态变了，这条提醒自然就消失或更新，不需要我们额外维护。
 *
 * 2. 提醒对家庭成员全员可见（都是全家要处理的事），所以不按 isOwner 隐藏；
 *    但点进去是去"编辑那条食材"，而冰箱只有创建人能改——
 *    所以普通成员点了若跳到编辑页会被后端拦，这里直接不让他跳（和冰箱列表一致）。
 *
 * 3. v1 只做两类冰箱提醒：临期/过期（按后端 3 天阈值算）+ 缺货。
 *    level 决定配色：danger（已过期/缺货）用危险色，warning（临期）用提醒色。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import { fetchAlerts, type Alert } from '../../services/alerts';
import { getCurrentSpace, getCurrentSpaceId, getCurrentSpaceName } from '../../utils/space-context';
import { showError } from '../../utils/format';

const alerts = ref<Alert[]>([]);
const loading = ref(true);
const hasSpace = ref(false);
const spaceName = ref('');
const isOwner = ref(false);

/** 列表顶部的短标签：过期 / 临期 / 缺货 */
function badge(a: Alert): string {
  return kindOf(a);
}

/** 筛选类别：全部 / 已过期 / 临期 / 缺货 */
const filters = ['全部', '已过期', '临期', '缺货'];
/** 当前选中的筛选，默认看全部 */
const activeFilter = ref('全部');

/** 这条提醒属于哪一类（与 badge 文案一致，作为筛选匹配依据） */
function kindOf(a: Alert): '已过期' | '临期' | '缺货' {
  if (a.type === 'fridge_out') return '缺货';
  return a.level === 'danger' ? '已过期' : '临期';
}

/** 按当前筛选算出来的可见列表（纯前端过滤，不重新请求后端） */
const filtered = computed<Alert[]>(() => {
  if (activeFilter.value === '全部') return alerts.value;
  return alerts.value.filter((a) => kindOf(a) === activeFilter.value);
});

async function load(): Promise<void> {
  loading.value = true;
  try {
    await ensureLogin();
    const spaceId = getCurrentSpaceId();
    spaceName.value = getCurrentSpaceName();
    isOwner.value = getCurrentSpace()?.myRole === 'admin';
    hasSpace.value = Boolean(spaceId);

    if (!spaceId) {
      alerts.value = [];
      activeFilter.value = '全部';
      return;
    }

    // 每次重新拉数据都回到"全部"，避免切换家庭后残留上一个家的筛选导致列表空掉
    activeFilter.value = '全部';
    alerts.value = await fetchAlerts(spaceId);
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

onShow(load);

/** 点提醒卡片：创建人跳去编辑那条食材，普通成员只能看（点了没反应，符合权限） */
function openAlert(a: Alert): void {
  if (!isOwner.value) return;
  if (!a.action) return;
  uni.navigateTo({ url: a.action });
}
</script>

<style scoped>
.alerts-page {
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

.tip { margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

/* 筛选药丸：横向滚动，多了也不挤。用原生 CSS 实现（overflow-x:auto），不用 scroll-view——
   和冰箱页一致：scroll-view 在 loading 切换导致整块重挂载时会抛 "scrollLeft of null"（DCloud 老问题）。 */
.filters { margin-top: var(--s-3); }
.filter-scroll { width: 100%; white-space: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.filter-scroll::-webkit-scrollbar { display: none; }
.filter-track { display: inline-flex; gap: var(--s-2); padding: 2rpx 0; }
.chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 24rpx;
}
.chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}

.list { margin-top: var(--s-3); display: flex; flex-direction: column; gap: var(--s-2); }

.card {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 严重级别配色：danger 走危险色，warning 走提醒色（令牌与冰箱页一致） */
.card.danger { background: var(--c-danger-bg); border-color: var(--c-danger-border); }
.card.warning { background: var(--c-warn-bg); border-color: var(--c-warn-border); }

/* 提醒图标：纯 CSS 矢量三角 + 感叹号（微信小程序不支持内联 svg，故用 CSS 画）。
   颜色随级别走令牌，不用 emoji——emoji 跨平台字体不一致、也拿不到设计令牌颜色。 */
.card-icon {
  position: relative;
  flex: 0 0 auto;
  width: 34rpx;
  height: 32rpx;
  border-left: 18rpx solid transparent;
  border-right: 18rpx solid transparent;
  border-bottom: 32rpx solid var(--c-warn);
}
.card-icon.danger { border-bottom-color: var(--c-danger); }
.card-icon.warning { border-bottom-color: var(--c-warn); }
.card-icon::after {
  content: '!';
  position: absolute;
  left: 50%;
  top: 8rpx;
  transform: translateX(-50%);
  color: #fff;
  font-size: 20rpx;
  font-weight: 700;
  line-height: 1;
}

.card-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: var(--s-1); }
.card-head { display: flex; align-items: center; gap: var(--s-2); }
.card-title {
  overflow: hidden;
  color: var(--c-text);
  font-size: 29rpx;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 顶部小标签：用和卡片一致的级别色，扫一眼区分"过期/临期/缺货" */
.card-badge {
  flex: 0 0 auto;
  padding: 2rpx var(--s-2);
  border-radius: var(--r-pill);
  font-size: 20rpx;
}
.card-badge.danger { background: var(--c-danger); color: #fff; }
.card-badge.warning { background: var(--c-warn); color: #fff; }
.card-detail {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 23rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 40rpx; line-height: 1; }

.empty { margin-top: 100rpx; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); }
.empty-text { color: var(--c-text-2); font-size: 27rpx; }
.empty-hint { color: var(--c-text-3); font-size: 23rpx; }
</style>
