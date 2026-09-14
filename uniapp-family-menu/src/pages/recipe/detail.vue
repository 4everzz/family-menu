<template>
  <view class="detail-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <!-- 头部：菜名 + 分类标签（不做占位图，分类只留文字） -->
      <view class="hero">
        <view class="hero-copy">
          <text class="hero-name">{{ recipe.name }}</text>
          <view class="hero-tags">
            <text class="tag">{{ recipe.categoryName }}</text>
          </view>
        </view>
      </view>

      <view class="block">
        <text class="block-title">简介</text>
        <text v-if="recipe.description" class="block-body">{{ recipe.description }}</text>
        <text v-else class="block-empty">还没有写简介。菜谱内容由创建人维护，可以提醒他来补充。</text>
      </view>

      <text v-if="metaLine" class="page-note">{{ metaLine }}</text>

      <!-- 这里刻意不放编辑入口：菜单页是"翻菜谱"的地方，
           改菜谱统一收在「我的 → 菜单管理」里。浏览和编辑分开，翻的时候不容易误触。 -->
      <text class="page-hint">要修改这道菜，请到「我的 → 菜单管理 → 菜品管理」</text>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 菜谱详情页（只读）。
 *
 * 为什么要有它？菜单页现在定位是"翻菜谱"，点开一道菜就该是"看看怎么做"，
 * 而不是直接进编辑器。以前点卡片直接进编辑页，翻菜单的时候手滑点开就进了表单，
 * 很容易误改；而且编辑器带着删除按钮，浏览场景下风险更大。
 *
 * 所以阅读和编辑彻底分开：
 *   菜单页 → 本页（只读）
 *   我的 → 菜单管理 → 菜品管理 → 编辑页（可改可删）
 */

import { computed, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import { fetchRecipe } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import { getCurrentSpaceId } from '../../utils/space-context';

const spaceId = ref('');
const recipeId = ref('');
const loading = ref(true);
const errorMessage = ref('');
const metaLine = ref('');

/** 空对象占位：模板里可以用 recipe.name 而不用满屏写可选链 */
const recipe = ref<Recipe>({
  id: '',
  spaceId: '',
  name: '',
  categoryId: '',
  categoryName: '',
  description: '',
  imageUrl: '',
  createdByName: '',
  createdBy: 0,
  updatedAt: '',
});


/**
 * 把后端返回的时间转成「2026年9月14日」这种好读的格式。
 *
 * 后端给的是 ISO 字符串（带时区）。这里只取到"日"这一级——
 * 对一道家常菜来说，精确到分钟没有意义，反而占地方。
 */
function formatDate(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();
    if (!spaceId.value) throw new Error('还没有选择家庭组');

    recipe.value = await fetchRecipe(spaceId.value, recipeId.value);

    const parts: string[] = [];
    if (recipe.value.createdByName) parts.push(`由 ${recipe.value.createdByName} 添加`);
    const updated = formatDate(recipe.value.updatedAt);
    if (updated) parts.push(`最后修改于 ${updated}`);
    metaLine.value = parts.join(' · ');

    uni.setNavigationBarTitle({ title: recipe.value.name || '菜谱' });
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

onLoad((options) => {
  recipeId.value = String(options?.id ?? '');
  void load();
});
</script>

<style scoped>
.detail-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.tip { display: block; margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-4);
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
  height: 72rpx;
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}

/* 头部：占位图 + 菜名，做成一张主卡片，视觉重心在这里 */
.hero {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.hero-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: var(--s-2); }
.hero-name {
  color: var(--c-text);
  font-size: 40rpx;
  font-weight: 500;
  line-height: 1.3;
  word-break: break-all;
}
.hero-tags { display: flex; flex-wrap: wrap; gap: var(--s-1); }
.tag {
  display: inline-flex;
  align-items: center;
  height: 48rpx;
  padding: 0 var(--s-2);
  border-radius: var(--r-pill);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: 23rpx;
}

/* 简介区块：正文部分行高放宽到 1.8，读起来不挤 */
.block {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.block-title { color: var(--c-text-3); font-size: 23rpx; }
.block-body {
  color: var(--c-text);
  font-size: 28rpx;
  line-height: 1.8;
  white-space: pre-wrap;
}
.block-empty { color: var(--c-text-2); font-size: 25rpx; line-height: 1.7; }

.page-note { display: block; margin-top: var(--s-3); color: var(--c-text-3); font-size: 22rpx; text-align: center; }
.page-hint {
  display: block;
  margin-top: var(--s-1);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
