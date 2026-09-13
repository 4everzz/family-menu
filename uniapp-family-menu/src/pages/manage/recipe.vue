<template>
  <view class="manage-page">
    <view class="page-head">
      <text class="page-title">菜品管理</text>
      <text class="page-desc">这里集中增删改菜谱。点某一道菜可以直接进去改，右边可以删。</text>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" @click="load">重试</view>
    </view>

    <template v-else>
      <!-- 分类筛选：横向滚动而不是换行铺开。
           分类数量由用户自己定，做成两行会把下面的列表挤下去 -->
      <scroll-view class="filter-scroll" scroll-x :show-scrollbar="false">
        <view class="filter-inner">
          <view
            class="filter-chip"
            :class="{ active: activeCategoryId === '' }"
            @click="activeCategoryId = ''"
          >
            全部 {{ recipes.length }}
          </view>
          <view
            v-for="item in categories"
            :key="item.id"
            class="filter-chip"
            :class="{ active: activeCategoryId === item.id }"
            @click="activeCategoryId = item.id"
          >
            {{ item.name }} {{ item.recipeCount }}
          </view>
        </view>
      </scroll-view>

      <view v-if="filtered.length" class="list">
        <view v-for="item in filtered" :key="item.id" class="row" @click="edit(item)">
          <view class="row-icon" :style="{ background: colorOf(item.categoryId) }">
            {{ emojiOf(item.categoryId) }}
          </view>
          <view class="row-main">
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta">{{ item.categoryName }}</text>
          </view>
          <view class="row-delete" @click.stop="remove(item)">删除</view>
        </view>
      </view>

      <view v-else class="empty-card">
        <text class="empty-text">
          {{ activeCategoryId ? '这个分类下还没有菜' : '还没有任何菜谱，点下面的按钮加第一道菜' }}
        </text>
      </view>

      <view class="add-btn" @click="add">+ 新增菜品</view>
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
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { fetchRecipes, deleteRecipe } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import { categoryColor, categoryEmoji } from '../../utils/category-visual';
import { getCurrentSpaceId } from '../../utils/space-context';
import { showError } from '../../utils/format';

const spaceId = ref('');
const categories = ref<Category[]>([]);
const recipes = ref<Recipe[]>([]);
const loading = ref(true);
const errorMessage = ref('');
const pending = ref(false);
/** 当前筛选的分类 ID，空字符串表示"全部" */
const activeCategoryId = ref('');

const colorOf = categoryColor;
const emojiOf = categoryEmoji;

const filtered = computed(() =>
  activeCategoryId.value
    ? recipes.value.filter((item) => item.categoryId === activeCategoryId.value)
    : recipes.value,
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
 * 删除。
 *
 * 二次确认不能省：本版本"任何家庭成员都能删任何菜"（见后端 RecipeService 的说明），
 * 权限上不设门槛，代价就用这道确认兜住——菜谱是全家一起攒的。
 */
function remove(item: Recipe): void {
  if (pending.value) return;
  uni.showModal({
    title: '删除这道菜',
    content: `确定要把「${item.name}」从家庭菜谱里删掉吗？删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: '#dc2626',
    success: async (result) => {
      if (!result.confirm) return;
      pending.value = true;
      uni.showLoading({ title: '删除中' });
      try {
        await deleteRecipe(spaceId.value, item.id);
        uni.showToast({ title: '已删除', icon: 'success' });
        await load();
      } catch (error) {
        showError(error instanceof Error ? error.message : '删除失败，请重试');
      } finally {
        uni.hideLoading();
        pending.value = false;
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
.page-title { color: var(--c-text); font-size: 40rpx; font-weight: 500; }
.page-desc { color: var(--c-text-2); font-size: 24rpx; line-height: 1.7; }

.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid #f7c1c1;
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.error-text { color: var(--c-danger); font-size: 27rpx; line-height: 1.6; }
.retry-btn {
  align-self: flex-start;
  display: flex;
  align-items: center;
  height: 72rpx;
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}

.filter-scroll { width: 100%; white-space: nowrap; }
.filter-inner { display: inline-flex; align-items: center; gap: var(--s-2); padding: var(--s-1) 0 var(--s-3); }
.filter-chip {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  height: 72rpx;
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
.row-icon {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 84rpx;
  height: 84rpx;
  border-radius: var(--r-sm);
  font-size: 40rpx;
  line-height: 1;
}
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

.row-delete {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 96rpx;
  height: var(--touch-min);
  padding: 0 var(--s-2);
  border: 2rpx solid #f7c1c1;
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-danger);
  font-size: 25rpx;
}

.empty-card {
  padding: 80rpx var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.empty-text { display: block; color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; text-align: center; }

.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 96rpx;
  margin-top: var(--s-3);
  border: 2rpx dashed var(--c-primary);
  border-radius: var(--r-md);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: 28rpx;
  font-weight: 500;
}
</style>
