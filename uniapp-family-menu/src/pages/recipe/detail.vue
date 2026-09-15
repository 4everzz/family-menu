<template>
  <view class="detail-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <!-- 头部：菜品图片（有才显示）+ 菜名 + 分类标签 -->
      <view class="hero">
        <image
          v-if="recipe.imageUrl"
          class="hero-image"
          :src="resolveFileUrl(recipe.imageUrl)"
          mode="aspectFit"
        />
        <view class="hero-copy">
          <view class="hero-title-row">
            <text class="hero-name">{{ recipe.name }}</text>
            <view class="fav-star" hover-class="tap" @click.stop="toggleFavorite">
              <image
                class="fav-star-img"
                :src="isFavorited ? '/static/icons/star-active.png' : '/static/icons/star.png'"
                mode="aspectFit"
              />
            </view>
          </view>
          <view class="hero-tags">
            <text class="tag">{{ recipe.categoryName }}</text>
            <!-- 「今天不做」：仍然看得到这道菜，只是暂时不能点 -->
            <text v-if="recipe.isSoldOut" class="tag tag-warn">今天不做</text>
          </view>
        </view>
      </view>

      <!-- 辣度：只在设了档位时才显示。默认那一档加重，因为它就是点单时不选时的结果 -->
      <view v-if="recipe.spiceOptions.length" class="block">
        <text class="block-title">辣度</text>
        <view class="spice-tags">
          <text
            v-for="level in recipe.spiceOptions"
            :key="level"
            class="tag"
            :class="{ 'tag-strong': level === (recipe.defaultSpice || recipe.spiceOptions[0]) }"
          >{{ level }}</text>
        </view>
        <text class="block-body">
          点单时不特别说明，就按「{{ recipe.defaultSpice || recipe.spiceOptions[0] }}」记。
        </text>
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
import { resolveFileUrl } from '../../services/http';
import { fetchRecipe } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import {
  favoriteRecipe,
  fetchFavoritedIds,
  fetchPartitions,
  unfavoriteRecipe,
} from '../../services/favorite';
import type { FavoritePartition } from '../../services/favorite';
import { getCurrentSpaceId } from '../../utils/space-context';

const spaceId = ref('');
const recipeId = ref('');
const loading = ref(true);
const errorMessage = ref('');
const metaLine = ref('');
/** 当前这道菜是否被我收藏 */
const isFavorited = ref(false);
/** 收藏分区列表（点星标收藏时让用户挑）。默认收藏夹 id 为 null，永远在第一位 */
const partitions = ref<FavoritePartition[]>([]);

/** 空对象占位：模板里可以用 recipe.name 而不用满屏写可选链 */
const recipe = ref<Recipe>({
  id: '',
  spaceId: '',
  name: '',
  categoryId: '',
  categoryName: '',
  description: '',
  imageUrl: '',
  spiceOptions: [],
  defaultSpice: '',
  isSoldOut: false,
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
    isFavorited.value = (await fetchFavoritedIds(spaceId.value)).has(recipe.value.id);
    partitions.value = await fetchPartitions();

    const parts: string[] = [];
    // 不显示"由谁添加"（用户明确要求）：家里做菜不关心这个，
    // 留着反而像在给每条菜谱记一笔账。只保留"最后修改于"——它回答的是
    // "这道菜是不是最近改过"，比"谁加的"有用。
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

async function toggleFavorite(): Promise<void> {
  // 已收藏：再点一下直接取消（最快路径，不用弹窗）
  if (isFavorited.value) {
    await doUnfavorite();
    return;
  }

  // 没收藏过：弹分区选择，让用户决定收藏到哪个分区
  const list = partitions.value.length
    ? partitions.value
    : [{ id: null, name: '默认收藏夹', count: 0, isDefault: true }];
  uni.showActionSheet({
    itemList: list.map((partition) => `收藏到「${partition.name}」`),
    success: async (result) => {
      const target = list[result.tapIndex];
      try {
        await favoriteRecipe(recipe.value.id, target.id);
        isFavorited.value = true;
        uni.showToast({ title: `已收藏到「${target.name}」`, icon: 'none' });
      } catch (error) {
        uni.showToast({
          title: error instanceof Error ? error.message : '收藏失败',
          icon: 'none',
        });
      }
    },
  });
}

/** 取消收藏 */
async function doUnfavorite(): Promise<void> {
  try {
    await unfavoriteRecipe(recipe.value.id);
    isFavorited.value = false;
    uni.showToast({ title: '已取消收藏', icon: 'none' });
  } catch (error) {
    uni.showToast({
      title: error instanceof Error ? error.message : '操作失败',
      icon: 'none',
    });
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
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 25rpx;
}

/* 头部卡片：图片在上、菜名在下（纵向堆叠）。
   ⚠️ 之前是横向排的，结果是图片按 width:100% 把整行吃满、菜名被挤成一条竖排小字。
   根因是"图片宽度"根本不归我们控制——用户传的是竖图、横图还是超宽图都有可能，
   横向并排时它总能抢到绝大部分空间。纵向堆叠对任何比例都稳。 */
.hero {
  overflow: hidden;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 头部图片：限定一个"正常"的头部尺寸（最大 420rpx 高），
   用 aspectFit 把整张图**等比例缩小**后完整放进去——
   不裁切、不放大，只缩放。竖图两边会留出一点底色边，横图上下会留一点底色边，
   都比把菜切掉一半强。四个圆角交给外层 .hero 的 overflow:hidden 裁 */
.hero-image {
  display: block;
  width: 100%;
  height: 600rpx;
  background: var(--c-muted);
}
.hero-copy {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
}
/* 菜名和收藏星标并排：星标放在详情页里，不在卡片上 */
.hero-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-2);
}
.hero-name {
  flex: 1;
  min-width: 0;
  color: var(--c-text);
  font-size: 40rpx;
  font-weight: 500;
  line-height: 1.3;
}
.fav-star {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--touch-min);
  height: var(--touch-min);
  margin: calc(-1 * var(--s-2)) calc(-1 * var(--s-2)) calc(-1 * var(--s-2)) 0;
}
.fav-star-img { width: 40rpx; height: 40rpx; }
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
/* 「今天不做」：用提醒色而不是危险色——它是随时能恢复的临时状态，不是出问题了 */
.tag-warn { background: var(--c-warn-bg); color: var(--c-warn-text); }
/* 默认辣度：实心主色，和其余档位拉开差别，一眼看出"不选时按这个记" */
.tag-strong { background: var(--c-primary); color: #fff; font-weight: 500; }
.spice-tags { display: flex; flex-wrap: wrap; gap: var(--s-1); }

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
