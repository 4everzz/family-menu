<template>
  <view class="favorites-page">
    <view v-if="loading" class="tip">正在读取收藏…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <text class="error-hint">收藏功能需要后端处于启动状态。</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <!--
        分区切换：默认收藏夹永远在第一位（后端保证，它的 id 是 null）。
        用横向滚动而不是换行——分区是用户自己建的，数量不受我们控制。
      -->
      <view class="partition-scroll">
        <view class="partition-inner">
          <view
            v-for="item in partitions"
            :key="String(item.id)"
            class="partition-chip"
            :class="{ active: activeId === item.id }"
            hover-class="tap"
            @click="switchPartition(item.id)"
          >
            {{ item.name }} {{ item.count }}
          </view>
        </view>
      </view>

      <view v-if="items.length" class="list">
        <view
          v-for="item in items"
          :key="item.recipeId"
          class="fav-card"
          hover-class="tap"
          @click="openDetail(item)"
        >
          <view class="fav-main">
            <text class="fav-name">{{ item.name }}</text>
            <text v-if="item.description" class="fav-desc">{{ item.description }}</text>
            <text class="fav-meta">{{ item.spaceName }}<template v-if="item.categoryName"> · {{ item.categoryName }}</template></text>
          </view>
          <view class="fav-actions">
            <text class="fav-move" hover-class="tap" @click.stop="promptMove(item)">移动</text>
            <text class="fav-remove" hover-class="tap" @click.stop="confirmUnfavorite(item)">取消收藏</text>
          </view>
        </view>
      </view>

      <view v-else class="empty-card">
        <text class="empty-title">{{ activeName }}还是空的</text>
        <text class="empty-copy">打开一道菜的详情页，点右上角的星标，它就会收藏到这里。</text>
        <view class="empty-btn" hover-class="tap" @click="goMenu">去菜单看看</view>
      </view>

      <!--
        分区管理：新建和删除都收在这里，而不是散在分区标签上——
        删除是个破坏性动作，藏进长按手势里用户永远发现不了。
      -->
      <view class="manage-card">
        <text class="manage-title">分区管理</text>
        <view class="manage-row" hover-class="tap" @click="promptCreate">
          <text class="manage-name">新建分区</text>
          <text class="manage-action">＋</text>
        </view>
        <view
          v-for="item in customPartitions"
          :key="String(item.id)"
          class="manage-row"
        >
          <text class="manage-name">{{ item.name }} · {{ item.count }} 道</text>
          <text class="manage-delete" hover-class="tap" @click="confirmDeletePartition(item)">删除</text>
        </view>
        <text class="manage-note">删除分区时，里面的收藏会自动退回「默认收藏夹」，不会丢。</text>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 我的收藏页（5B-1）。
 *
 * 收藏是**个人私有域**的数据：这个页面里的东西只跟当前登录的用户走，
 * 和"当前家庭组"无关——收藏可能来自不同的家，所以每条都带家庭组名。
 *
 * 默认收藏夹的 id 是 null（后端把它设计成"没有分区"这个状态，不落库），
 * 所以切换分区时用 null 做默认栏的标识，而不是造一个假 ID 出来。
 */
import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import {
  createPartition,
  deletePartition,
  favoriteRecipe,
  fetchFavorites,
  fetchPartitions,
  unfavoriteRecipe,
} from '../../services/favorite';
import type { FavoriteItem, FavoritePartition } from '../../services/favorite';
import { DANGER, PRIMARY } from '../../utils/theme';
import { showError } from '../../utils/format';

const loading = ref(true);
const errorMessage = ref('');
const partitions = ref<FavoritePartition[]>([]);
const items = ref<FavoriteItem[]>([]);
/** 当前选中的分区。null = 默认收藏夹 */
const activeId = ref<number | null>(null);

/** 自定义分区（分区管理卡片里列出、可删除的就是这些） */
const customPartitions = computed(() => partitions.value.filter((item) => !item.isDefault));

const activeName = computed(
  () => partitions.value.find((item) => item.id === activeId.value)?.name ?? '默认收藏夹',
);

async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    await ensureLogin();
    partitions.value = await fetchPartitions();
    items.value = await fetchFavorites(activeId.value);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取收藏失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

async function switchPartition(partitionId: number | null): Promise<void> {
  activeId.value = partitionId;
  items.value = await fetchFavorites(partitionId);
}

function openDetail(item: FavoriteItem): void {
  uni.navigateTo({ url: `/pages/recipe/detail?id=${item.recipeId}` });
}

/** 空态引导：收藏页在页面栈里可能不是从菜单页进来的，返回失败时切到菜单标签页兜底 */
function goMenu(): void {
  if (getCurrentPages().length > 1) {
    uni.navigateBack();
  } else {
    uni.switchTab({ url: '/pages/menu/index' });
  }
}

/**
 * 移动到其它分区：用 ActionSheet 让用户直接挑，而不是让他去分区管理里倒腾。
 * 排除当前所在的分区（移到自己已经在的地方没有意义）。
 */
function promptMove(item: FavoriteItem): void {
  const targets = partitions.value.filter((p) => p.id !== activeId.value);
  if (!targets.length) {
    uni.showToast({ title: '先在下方新建一个分区', icon: 'none' });
    return;
  }
  uni.showActionSheet({
    itemList: targets.map((p) => p.name),
    success: async (result) => {
      const target = targets[result.tapIndex];
      try {
        // 复用"收藏"接口：已收藏时再调一次就是挪分区
        await favoriteRecipe(item.recipeId, target.id);
        items.value = await fetchFavorites(activeId.value);
        await refreshCounts();
        uni.showToast({ title: `已移动到「${target.name}」`, icon: 'none' });
      } catch (error) {
        showError(error);
      }
    },
  });
}

/** 取消收藏：先把话说清楚（和删除类操作一个规矩），再动手 */
function confirmUnfavorite(item: FavoriteItem): void {
  uni.showModal({
    title: '取消收藏',
    content: `把「${item.name}」从收藏里移除吗？`,
    confirmText: '移除',
    confirmColor: PRIMARY,
    success: async (result) => {
      if (!result.confirm) return;
      try {
        await unfavoriteRecipe(item.recipeId);
        await switchPartition(activeId.value);
        await refreshCounts();
      } catch (error) {
        showError(error);
      }
    },
  });
}

/** 新建分区：用可输入的弹窗，省掉一个单独的表单页 */
function promptCreate(): void {
  uni.showModal({
    title: '新建分区',
    editable: true,
    placeholderText: '例如：想吃、孩子爱吃',
    confirmColor: PRIMARY,
    success: async (result) => {
      if (!result.confirm) return;
      const name = (result.content ?? '').trim();
      if (!name) return;
      try {
        await createPartition(name);
        await reloadPartitions();
      } catch (error) {
        showError(error);
      }
    },
  });
}

/** 删除分区：必须说清代价（里面的收藏会退回默认栏，而不是消失） */
function confirmDeletePartition(item: FavoritePartition): void {
  uni.showModal({
    title: '删除分区',
    content: `删除「${item.name}」吗？里面的 ${item.count} 道收藏会退回「默认收藏夹」。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;
      try {
        await deletePartition(item.id as number);
        // 如果删掉的是当前正在看的分区，先回到默认栏，避免停留在已不存在的分区上
        if (activeId.value === item.id) activeId.value = null;
        await reloadPartitions();
        items.value = await fetchFavorites(activeId.value);
      } catch (error) {
        showError(error);
      }
    },
  });
}

/** 只刷新分区（计数），不动当前列表——收藏/取消后调用 */
async function refreshCounts(): Promise<void> {
  partitions.value = await fetchPartitions();
}

async function reloadPartitions(): Promise<void> {
  partitions.value = await fetchPartitions();
}

onShow(load);
</script>

<style scoped>
.favorites-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
  background: var(--c-bg);
}
.tip { display: block; margin-top: var(--s-6); color: var(--c-text-3); font-size: 24rpx; text-align: center; }
.error-card { display: flex; flex-direction: column; gap: var(--s-2); margin-top: var(--s-4); padding: var(--s-4) var(--s-3); border: 2rpx solid var(--c-danger-border); border-radius: var(--r-lg); background: var(--c-surface); }
.error-text { color: var(--c-danger); font-size: 27rpx; font-weight: 500; }
.error-hint { color: var(--c-text-2); font-size: 23rpx; line-height: 1.6; }
.retry-btn { display: flex; align-items: center; justify-content: center; min-height: var(--touch-min); margin-top: var(--s-2); border-radius: var(--r-md); background: var(--c-primary); color: #ffffff; font-size: 26rpx; }

/* 分区条横向滚动用原生 CSS（overflow-x:auto）代替 scroll-view——
   规避 scroll-view 在重挂载时写 scrollLeft 报 null 的框架问题。
   inner 用 inline-flex 才能随内容撑开、让父级出现横向滚动条。 */
.partition-scroll { flex: 0 0 auto; width: 100%; overflow-x: auto; white-space: nowrap; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.partition-scroll::-webkit-scrollbar { display: none; }
.partition-inner { display: inline-flex; gap: var(--s-2); padding-bottom: var(--s-1); }
.partition-chip {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  min-height: var(--touch-min);
  padding: 0 var(--s-4);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 25rpx;
}
.partition-chip.active { border-color: var(--c-primary); background: var(--c-primary-bg); color: var(--c-primary); font-weight: 500; }

.list { display: flex; flex-direction: column; gap: var(--s-2); margin-top: var(--s-3); }
.fav-card {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.fav-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.fav-name { overflow: hidden; color: var(--c-text); font-size: 29rpx; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.fav-desc { overflow: hidden; color: var(--c-text-2); font-size: 23rpx; text-overflow: ellipsis; white-space: nowrap; }
.fav-meta { overflow: hidden; color: var(--c-text-3); font-size: 22rpx; text-overflow: ellipsis; white-space: nowrap; }
.fav-actions { flex: 0 0 auto; display: flex; align-items: center; gap: var(--s-3); }
.fav-move { padding: 30rpx 0; margin: -30rpx 0; color: var(--c-primary); font-size: 23rpx; }
.fav-remove { padding: 30rpx 0; margin: -30rpx 0; color: var(--c-text-2); font-size: 23rpx; }

.empty-card { display: flex; flex-direction: column; gap: var(--s-2); margin-top: 140rpx; padding: var(--s-5) var(--s-4); text-align: center; }
.empty-title { color: var(--c-text); font-size: 30rpx; font-weight: 500; }
.empty-copy { color: var(--c-text-2); font-size: 24rpx; line-height: 1.7; }
.empty-btn {
  align-self: center;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  margin-top: var(--s-2);
  padding: 0 var(--s-5);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #ffffff;
  font-size: 26rpx;
  font-weight: 500;
}

.manage-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-5);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.manage-title { margin-bottom: var(--s-1); color: var(--c-text-2); font-size: 23rpx; }
.manage-row { display: flex; align-items: center; justify-content: space-between; min-height: var(--touch-min); padding: 0 var(--s-1); }
.manage-name { color: var(--c-text); font-size: 26rpx; }
.manage-action { color: var(--c-primary); font-size: 32rpx; }
.manage-delete { padding: 30rpx var(--s-2); margin: -30rpx calc(-1 * var(--s-2)); color: var(--c-danger); font-size: 23rpx; }
.manage-note { margin-top: var(--s-1); color: var(--c-text-3); font-size: 22rpx; line-height: 1.6; }
</style>
