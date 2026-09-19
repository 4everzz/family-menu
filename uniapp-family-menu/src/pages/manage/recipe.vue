<template>
  <view class="manage-page" :class="{ 'with-bar': selectMode }">
    <view class="page-head">
      <view class="page-head-top">
        <!-- 左边放状态而不是标题（2026-09-19）：
             原生导航栏已经写着「菜品管理」，页内再写一遍是同一句话说两遍、
             还白占首屏。换成"这个列表现在有多少道菜"，选中时换成已选数。 -->
        <text class="page-status">
          {{ selectMode ? `已选 ${pickedIds.length} 道` : `共 ${recipes.length} 道菜` }}
        </text>
        <view class="head-actions">
          <!-- 新增：2026-09-19 从列表最下方挪到这里（用户反馈"新增菜品还需要一直下滑"）。
               它是最常用的动作，所以用实心主色；批量删除是低频且偏破坏性的操作，用描边弱化。
               选中的状态（selectMode）下不给新增，避免"一边勾删除一边加菜"。 -->
          <view v-if="!selectMode" class="head-btn primary" hover-class="tap" @click="add">
            新增菜品
          </view>
          <!-- 批量删除入口：每行挂一个删除键太臃肿，改成右上角一个入口 -->
          <view v-if="recipes.length" class="head-btn" hover-class="tap" @click="toggleSelectMode">
            {{ selectMode ? '取消' : '批量删除' }}
          </view>
        </view>
      </view>
      <!-- 只留真正有用的一句；选中模式下由底部操作栏（全选 / 已选 / 删除）承担指引，
           这里不重复说嘴 -->
      <text v-if="!selectMode" class="page-desc">点某一道菜可以直接进去改。</text>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <!-- 分类筛选：横向滚动而不是换行铺开。
           分类数量由用户自己定，做成两行会把下面的列表挤下去 -->
      <view class="filter-scroll">
        <view class="filter-inner">
          <view
            class="filter-chip"
            :class="{ active: activeCategoryId === '' }"
            hover-class="tap"
            @click="activeCategoryId = ''"
          >
            全部 {{ recipes.length }}
          </view>
          <view
            v-for="item in categories"
            :key="item.id"
            class="filter-chip"
            :class="{ active: activeCategoryId === item.id }"
            hover-class="tap"
            @click="activeCategoryId = item.id"
          >
            {{ item.name }} {{ item.recipeCount }}
          </view>
        </view>
      </view>

      <view v-if="filtered.length" class="list">
        <view
          v-for="item in filtered"
          :key="item.id"
          class="row"
          :class="{ picked: isPicked(item.id) }"
          hover-class="tap"
          @click="onRowTap(item)"
        >
          <view v-if="selectMode" class="check" :class="{ on: isPicked(item.id) }" />
          <view class="row-main">
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta">{{ item.categoryName }}</text>
          </view>
          <!-- 普通模式下给个箭头，提示"这行能点进去改"；选择模式下整行都是勾选区 -->
          <text v-if="!selectMode" class="row-arrow">›</text>
        </view>
      </view>

      <view v-else class="empty-card">
        <text class="empty-text">
          {{ activeCategoryId ? '这个分类下还没有菜，点右上角「新增菜品」加一道'
             : '还没有任何菜谱，点右上角「新增菜品」加第一道菜' }}
        </text>
      </view>

      <!-- 批量操作栏：固定在底部（本页不是 tabBar 页，bottom:0 就是屏幕底） -->
      <view v-if="selectMode" class="select-bar">
        <view class="select-all" hover-class="tap" @click="toggleAll">
          {{ allPicked ? '取消全选' : '全选' }}
        </view>
        <text class="select-count">已选 {{ pickedIds.length }} 道</text>
        <view
          class="select-delete"
          :class="{ disabled: !pickedIds.length }"
          hover-class="tap"
          @click="removeSelected"
        >删除</view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 菜品管理页：集中增删改菜谱。
 *
 * 为什么单独开一页，而不是把编辑入口留在菜单页？
 *   菜单页是"翻菜谱"的地方——家里人吃饭前翻一翻、想做什么菜看一眼。
 *   编辑是低频且有破坏性的操作（尤其删除），和浏览混在一起，
 *   翻的时候手滑点开就进了表单，风险大。
 *   所以职责切开：菜单页只读，改菜统一来这里。
 *
 * 删除交互（2026-09-18 改）：
 *   以前每行挂一个红「删除」，24 道菜就是 24 个红按钮，又吵又占地方。
 *   改成右上角一个「批量删除」入口 → 勾选若干条 → 底部删除 → 二次确认（列出所选菜名）。
 *   单条删除仍然可用：进编辑页里删（那道菜自己的「删除」按钮还在）。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { fetchRecipes, deleteRecipe } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import { DANGER } from '../../utils/theme';
import { getCurrentSpaceId } from '../../utils/space-context';

const spaceId = ref('');
const categories = ref<Category[]>([]);
const recipes = ref<Recipe[]>([]);
const loading = ref(true);
const errorMessage = ref('');
const pending = ref(false);
/** 当前筛选的分类 ID，空字符串表示"全部" */
const activeCategoryId = ref('');
/** 是否处于批量选择模式 */
const selectMode = ref(false);
/** 已勾选的菜谱 ID */
const pickedIds = ref<string[]>([]);


const filtered = computed(() =>
  activeCategoryId.value
    ? recipes.value.filter((item) => item.categoryId === activeCategoryId.value)
    : recipes.value,
);

/** 当前筛选出来的菜是否全被勾上了（用来切换"全选/取消全选"） */
const allPicked = computed(
  () => filtered.value.length > 0 && filtered.value.every((item) => pickedIds.value.includes(item.id)),
);

async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();
    if (!spaceId.value) throw new Error('还没有选择家庭组');

    // 菜谱接口一次就带回分类清单，不用再单独请求一次分类接口
    const list = await fetchRecipes(spaceId.value);
    categories.value = list.categories;
    recipes.value = list.recipes;

    // 如果当前筛的分类已经被删掉了，自动退回"全部"，免得看到一片空白还以为出错了
    if (activeCategoryId.value && !list.categories.some((item) => item.id === activeCategoryId.value)) {
      activeCategoryId.value = '';
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/** 新增：不带 id 进编辑页，就是新增模式 */
function add(): void {
  uni.navigateTo({ url: '/pages/recipe/edit' });
}

/** 编辑：带上 id 进同一个编辑页 */
function edit(item: Recipe): void {
  uni.navigateTo({ url: `/pages/recipe/edit?id=${item.id}` });
}

/**
 * 删除（2026-09-18 改成批量）。
 *
 * 以前每行挂一个「删除」按钮：24 道菜就是 24 个红色按钮，列表又吵又占地方。
 * 现在右上角一个入口进"选择模式"，勾一条或多条再删。
 *
 * 为什么逐个调删除接口，而不是新加一个批量接口？
 *   现有的删除接口本来就带归属与权限校验，复用它少一条路径、少一处可能出错的地方；
 *   菜量是几十条量级，逐个删的开销可以接受。
 *   代价是可能"删了一半"——所以失败的单独收集起来如实告诉用户，不假装全成功。
 *
 * 二次确认不能省：本版本"任何家庭成员都能删任何菜"（见后端 RecipeService 的说明），
 * 权限上不设门槛，代价就用这道确认兜住——菜谱是全家一起攒的。
 * 确认框里**把所选菜名列出来**，删错了当场能看出来。
 */
function toggleSelectMode(): void {
  selectMode.value = !selectMode.value;
  // 进和出都清空：免得下次进来还留着上一轮的勾选，一按删除删错东西
  pickedIds.value = [];
}

function isPicked(id: string): boolean {
  return pickedIds.value.includes(id);
}

/** 普通模式点行进编辑页；选择模式点行就是勾选/取消 */
function onRowTap(item: Recipe): void {
  if (!selectMode.value) {
    edit(item);
    return;
  }
  pickedIds.value = isPicked(item.id)
    ? pickedIds.value.filter((id) => id !== item.id)
    : [...pickedIds.value, item.id];
}

/** 全选 / 取消全选：只作用在当前筛选出来的这些菜上（所见即所选） */
function toggleAll(): void {
  pickedIds.value = allPicked.value ? [] : filtered.value.map((item) => item.id);
}

/** 弹窗里列菜名：超过 5 道只列前 5 道 + 共 N 道，否则弹窗会长到看不完 */
function nameList(names: string[]): string {
  const SHOW = 5;
  if (names.length <= SHOW) return names.join('、');
  return `${names.slice(0, SHOW).join('、')} 等 ${names.length} 道菜`;
}

function removeSelected(): void {
  if (pending.value || !pickedIds.value.length) return;
  const targets = filtered.value.filter((item) => isPicked(item.id));
  if (!targets.length) return;

  uni.showModal({
    title: `删除 ${targets.length} 道菜`,
    content: `确定要删除以下菜品吗？\n\n${nameList(targets.map((item) => item.name))}\n\n删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;

      pending.value = true;
      uni.showLoading({ title: '删除中', mask: true });
      const failed: string[] = [];
      try {
        for (const item of targets) {
          try {
            await deleteRecipe(spaceId.value, item.id);
          } catch {
            // 单条失败不打断整批——先尽力删完，最后统一汇报
            failed.push(item.name);
          }
        }
      } finally {
        uni.hideLoading();
        pending.value = false;
      }

      selectMode.value = false;
      pickedIds.value = [];
      await load();

      if (failed.length) {
        uni.showModal({
          title: '有没删掉的',
          content: `这些没能删掉：${failed.join('、')}。可能是网络问题，稍后可以再试。`,
          showCancel: false,
        });
      } else {
        uni.showToast({ title: `已删除 ${targets.length} 道`, icon: 'success' });
      }
    },
  });
}

// onShow：从编辑页返回时自动刷新，改完的菜名/分类立刻能看见
onShow(() => {
  void load();
});
</script>

<style scoped>
.manage-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.tip { display: block; margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

.page-head { display: flex; flex-direction: column; gap: var(--s-1); margin: 0 var(--s-1) var(--s-3); }
.page-head-top { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); }
/* 状态行（取代原来的页内标题）：与右边按钮同高，视觉上是一条工具条 */
.page-status { color: var(--c-text-2); font-size: 23rpx; }
.page-desc { color: var(--c-text-3); font-size: 22rpx; line-height: 1.5; }
/* 页头右上角的动作（批量删除 / 取消） */
.head-btn {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: 64rpx;
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 24rpx;
}

.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-danger-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.error-text { color: var(--c-danger); font-size: 27rpx; line-height: 1.6; }
.retry-btn {
  align-self: flex-start;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}

/* 分类筛选条横向滚动用原生 CSS（overflow-x:auto）代替 scroll-view，
   规避 scroll-view 重挂载时写 scrollLeft 报 null 的框架问题 */
.filter-scroll { width: 100%; white-space: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
.filter-scroll::-webkit-scrollbar { display: none; }
.filter-inner { display: inline-flex; align-items: center; gap: var(--s-2); padding: var(--s-1) 0 var(--s-3); }
.filter-chip {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 25rpx;
}
.filter-chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}

.list {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 128rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.row:last-child { border-bottom: none; }
.row-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.row-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 30rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-meta { color: var(--c-text-2); font-size: 23rpx; }

/* 勾中的行加一层浅底，扫一眼就知道选了哪几条 */
.row.picked { background: var(--c-primary-bg); }

/* 勾选框：纯 CSS（对勾是两条边转 45° 出来的），不用图片也不用 emoji */
.check {
  position: relative;
  flex: 0 0 auto;
  width: 40rpx;
  height: 40rpx;
  border: 2rpx solid var(--c-border-strong);
  border-radius: 50%;
  background: var(--c-surface);
  box-sizing: border-box;
}
.check.on { border-color: var(--c-primary); background: var(--c-primary); }
.check.on::after {
  content: '';
  position: absolute;
  left: 13rpx;
  top: 7rpx;
  width: 9rpx;
  height: 17rpx;
  border: 3rpx solid #fff;
  border-top: 0;
  border-left: 0;
  transform: rotate(45deg);
}

/* 代替原来的行内「删除」键：一个箭头，说明"这行点进去能改" */
.row-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 40rpx; line-height: 1; }

/* 批量操作栏 */
.select-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-2) var(--s-3) calc(var(--s-3) + env(safe-area-inset-bottom));
  border-top: 2rpx solid var(--c-border);
  background: var(--c-surface);
  box-sizing: border-box;
}
.select-all {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-2);
  color: var(--c-text-2);
  font-size: 25rpx;
}
.select-count { flex: 1; min-width: 0; color: var(--c-text-2); font-size: 25rpx; }
.select-delete {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-danger);
  color: #fff;
  font-size: 26rpx;
  font-weight: 500;
}
/* 一条没选就是不可用状态（点了也不会有反应，见 removeSelected 的早退） */
.select-delete.disabled { background: var(--c-muted); color: var(--c-text-3); }

/* 底部有操作栏时给页面留出空间，别让最后一行被盖住 */
.manage-page.with-bar { padding-bottom: calc(220rpx + env(safe-area-inset-bottom)); }

.empty-card {
  padding: 80rpx var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.empty-text { display: block; color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; text-align: center; }

/* 右上角的动作组：新增 + 批量删除。两个都是药丸形小按钮，
   一实一虚形成层次——新增是日常高频动作（实心主色），批量删除低频（描边）。
   实测两个按钮 + 标题在 360px 宽的手机上一行放得下（约 248px / 可用 337px）。 */
.head-actions { flex: 0 0 auto; display: flex; align-items: center; gap: var(--s-2); }
.head-btn.primary {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
}
</style>
