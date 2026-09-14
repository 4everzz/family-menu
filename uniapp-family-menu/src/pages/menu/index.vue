<template>
  <view class="menu-page">
    <!--
      页头：**家庭名就是这一页的标题**。
      菜单页展示的是"这个家的菜谱"，所以"在看哪个家"应该是页面的身份，
      而不是一块孤零零的卡片——之前那张卡只有一个名字，
      外框和阴影把一句话包成了相框，还白占了第一屏近 120rpx。

      只显示，**不提供切换**：切换属于配置类动作，统一收在「我的 → 设置」里。

      右侧只放分类数、不放菜数：菜数在下面的列表头上已经有了，
      但那个数字的含义不同（是"当前筛选下有几道"），两个菜数并排容易看混。
    -->
    <view class="page-head">
      <text class="page-title">{{ spaceName || '未加入家庭组' }}</text>
      <text v-if="spaceId && categories.length" class="page-subtitle">
        {{ categories.length }} 个分类
      </text>
    </view>

    <view v-if="loading" class="tip">正在读取菜谱…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <text class="error-hint">
        菜谱功能需要后端处于启动状态；在微信开发者工具里还需勾选「不校验合法域名」。
      </text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <view v-else-if="!spaceId" class="empty-card">
      <text class="empty-title">还没有家庭组</text>
      <text class="empty-copy">
        菜谱是全家共享的。去「我的 → 设置 → 切换家庭」创建一个家庭组，或让家人把邀请码发给你。
      </text>
      <view class="empty-btn" hover-class="tap" @click="goSettings">前往设置</view>
    </view>

    <template v-else>
      <view class="search-row">
        <input
          v-model="keyword"
          class="search-input"
          placeholder="搜索菜名或简介"
          placeholder-class="search-placeholder"
          confirm-type="search"
        />
        <text v-if="keyword" class="clear-search" hover-class="tap" @click="keyword = ''">清除</text>
      </view>

      <view class="menu-layout">
        <!-- 分类侧栏：条目 = 全部 + 这个家的分类，顺序完全照用后端 -->
        <scroll-view class="category-sidebar" scroll-y>
          <view
            class="category-button"
            :class="{ active: activeCategoryId === '' }"
            hover-class="tap"
            @click="activeCategoryId = ''"
          >
            <text class="category-name">全部</text>
            <text class="category-count">{{ recipes.length }}</text>
          </view>
          <view
            v-for="item in categories"
            :key="item.id"
            class="category-button"
            :class="{ active: activeCategoryId === item.id }"
            hover-class="tap"
            @click="activeCategoryId = item.id"
          >
            <text class="category-name">{{ item.name }}</text>
            <text class="category-count">{{ item.recipeCount }}</text>
          </view>
        </scroll-view>

        <scroll-view class="recipe-area" scroll-y>
          <view class="section-head">
            <text class="section-title">{{ activeCategoryName }}</text>
            <text class="section-count">{{ filtered.length }} 道菜</text>
          </view>

          <view v-if="filtered.length" class="recipe-list">
            <view v-for="item in filtered" :key="item.id" class="recipe-card" hover-class="tap" @click="openDetail(item)">
              <!-- 有图的菜显示缩略图；没图的就纯文字，不留空占位（和分类色块一个道理） -->
              <image
                v-if="item.imageUrl"
                class="recipe-photo"
                :src="resolveFileUrl(item.imageUrl)"
                mode="aspectFill"
              />
              <view class="recipe-copy">
                <text class="recipe-name">{{ item.name }}</text>
                <text class="recipe-desc">{{ item.description || '还没写简介' }}</text>
                <text class="recipe-meta">{{ metaText(item) }}</text>
              </view>
              <!--
                收藏星标：点一下收藏进默认栏，再点一下取消。
                @click.stop 是关键——不然点星星会同时把卡片点开，跳去详情页。
              -->
              <view class="fav-star" hover-class="tap" @click.stop="toggleFavorite(item)">
                <image
                  class="fav-star-img"
                  :src="favoritedIds.has(item.id) ? '/static/icons/star-active.png' : '/static/icons/star.png'"
                  mode="aspectFit"
                />
              </view>
              <text class="recipe-arrow">›</text>
            </view>
          </view>

          <view v-else class="content-state">
            <template v-if="recipes.length">没有找到相关菜谱</template>
            <template v-else-if="!categories.length">
              这个家还没有分类。先去「我的 → 菜单管理 → 分类管理」建一个，才能添加菜谱。
            </template>
            <template v-else>这个家还没有菜谱。</template>
          </view>

          <view class="bottom-space" />
        </scroll-view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 菜单页 = 家庭菜谱库（**纯浏览**）。
 *
 * 改造说明：
 *   这个页面原本是「商家点餐页」的骨架——必须先扫码进店、看某家店卖什么、加购物车结算。
 *   按产品定位（个人生活工作台），菜单应该是「我当前这个家庭组共享的菜」，
 *   所以扫码进店那道门被整个去掉了，改为直接读当前家庭组的菜谱。
 *
 *   后来又把编辑能力从这里拿走了：
 *   翻菜谱是每天都要做的事，改菜谱一个月未必有一次，而且删除是不可逆的。
 *   两者混在一起，翻的时候手滑就会进表单甚至误删。
 *   所以现在这里只读——点卡片进的是只读详情页；
 *   增删改统一收在「我的 → 菜单管理」里。
 *
 *   旧的商家代码（扫码进店 / 购物车 / 订单 / 商家登录）已在转型清理时一并删除，
 *   仓库里现在只剩家庭版这一套代码。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { favoriteRecipe, fetchFavoritedIds, unfavoriteRecipe } from '../../services/favorite';
import { resolveFileUrl } from '../../services/http';
import { fetchRecipes } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import { showError } from '../../utils/format';
import { getCurrentSpaceId, getCurrentSpaceName, resolveCurrentSpace } from '../../utils/space-context';

const spaceId = ref('');
const spaceName = ref('');
const categories = ref<Category[]>([]);
const recipes = ref<Recipe[]>([]);
/** 我在这个家里已收藏的菜谱 ID。Set 只为 O(1) 判断"这颗星亮不亮" */
const favoritedIds = ref<Set<string>>(new Set());
/** 当前选中的分类 ID。空字符串代表「全部」，不是后端给的真实分类 */
const activeCategoryId = ref('');
const keyword = ref('');
const loading = ref(true);
const errorMessage = ref('');
/** 是否已成功加载过一次：用来区分「首次进入显示加载中」和「从别处回来时静默刷新」 */
const loadedOnce = ref(false);


/** 当前分类的名字，显示在右侧列表的标题上 */
const activeCategoryName = computed(() => {
  if (!activeCategoryId.value) return '全部';
  return categories.value.find((item) => item.id === activeCategoryId.value)?.name || '全部';
});

/** 关键词匹配：菜名或简介里出现就算命中 */
function matchKeyword(item: Recipe, search: string): boolean {
  if (!search) return true;
  return item.name.includes(search) || item.description.includes(search);
}

/** 当前该显示哪些菜：分类 + 关键词两层过滤（纯本地，输入即时响应） */
const filtered = computed(() =>
  recipes.value.filter(
    (item) =>
      (!activeCategoryId.value || item.categoryId === activeCategoryId.value) &&
      matchKeyword(item, keyword.value.trim()),
  ),
);

/** 卡片底部那行小字：分类 + 谁加的（后端查不到昵称时就只显示分类） */
function metaText(item: Recipe): string {
  return item.createdByName ? `${item.categoryName} · ${item.createdByName} 加的` : item.categoryName;
}

/**
 * 加载菜谱。
 *
 * 每次进入页面都会重新拉一次，因为可能在别处改了数据（比如刚从菜品管理页返回）。
 * 第二次起不显示「加载中」，直接用旧内容顶着，拉回来再替换——避免页面闪一下。
 */
async function load(): Promise<void> {
  loading.value = !loadedOnce.value;
  errorMessage.value = '';
  try {
    // 先确保登录态：首次进入或令牌过期时会自动静默登录
    await ensureLogin();
    // 校正「当前家庭」：缓存里的家庭组可能已经不存在了（被解散、自己被移出），
    // 这里会自动回退到另一个可用的家庭组，或者清空
    await resolveCurrentSpace();
    spaceId.value = getCurrentSpaceId();
    spaceName.value = getCurrentSpaceName();

    // 一个家庭组都没有：不请求菜谱，让页面显示引导
    if (!spaceId.value) {
      recipes.value = [];
      categories.value = [];
      return;
    }

    const list = await fetchRecipes(spaceId.value);
    categories.value = list.categories;
    recipes.value = list.recipes;
    // 星标状态单独查：收藏是个人私有域，跟菜谱列表是两回事
    favoritedIds.value = await fetchFavoritedIds(spaceId.value);
    loadedOnce.value = true;

    // 当前选中的分类如果已经不在清单里了（比如在「分类管理」里把它删了），回到「全部」——
    // 否则用户会停在一个人永远看不到菜的标签上，还以为菜全丢了
    if (
      activeCategoryId.value &&
      !list.categories.some((item) => item.id === activeCategoryId.value)
    ) {
      activeCategoryId.value = '';
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取菜谱失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/**
 * 去设置页。
 *
 * 菜单页刻意不提供"切换家庭"入口——那是配置类动作，统一收在设置里。
 * 这里唯一需要它的地方是"一个家庭组都没有"时的引导：
 * 那时用户需要一条通往"创建 / 加入"的路，否则页面就成了死胡同。
 */
function goSettings(): void {
  uni.navigateTo({ url: '/pages/settings/index' });
}

/** 打开菜谱详情（只读）。要改的话去「我的 → 菜单管理 → 菜品管理」 */
function openDetail(item: Recipe): void {
  uni.navigateTo({ url: `/pages/recipe/detail?id=${item.id}` });
}

/**
 * 收藏 / 取消收藏（收藏进「默认收藏夹」）。
 *
 * 改完 Set 之后**整体换一个新 Set**，而不是只调 add/delete：
 * Vue 3 的响应式虽然能追踪 Set，但整只替换最稳，不会出现"星星不亮"的诡异问题。
 * 换分区不在这里做——收藏页里有「移动」入口，菜单页只负责最快的那一步。
 */
async function toggleFavorite(item: Recipe): Promise<void> {
  try {
    if (favoritedIds.value.has(item.id)) {
      await unfavoriteRecipe(item.id);
      favoritedIds.value = new Set([...favoritedIds.value].filter((id) => id !== item.id));
      uni.showToast({ title: '已取消收藏', icon: 'none' });
    } else {
      await favoriteRecipe(item.id, null);
      favoritedIds.value = new Set([...favoritedIds.value, item.id]);
      uni.showToast({ title: '已收藏到「默认收藏夹」', icon: 'none' });
    }
  } catch (error) {
    showError(error);
  }
}

onShow(load);
</script>

<style scoped>
/* 整页用 flex 纵向布局：这样中间的滚动区能自己撑满剩余高度，
   不用去硬算 calc(100vh - 多少 rpx)，换个机型也不会歪 */
.menu-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: var(--s-4) var(--s-3) 0;
  box-sizing: border-box;
}

/* 页头：标题 + 右侧分类数。刻意不加边框和底——它是"页面身份"，
   不是一张卡片；套上框反而又变回那个占位块了 */
.page-head {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
  /* 不加左右内边距：要和下面的搜索框、卡片严格左边对齐。
     标题只要比它们多缩进一点，边缘就会看出错位 */
}
.page-title {
  overflow: hidden;
  color: var(--c-text);
  font-size: 40rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.page-subtitle { flex: 0 0 auto; color: var(--c-text-2); font-size: 23rpx; }

.tip { display: block; margin-top: var(--s-5); color: var(--c-text-3); font-size: 24rpx; text-align: center; }

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
.error-text { color: var(--c-danger); font-size: 27rpx; font-weight: 500; }
.error-hint { color: var(--c-text-2); font-size: 23rpx; line-height: 1.6; }
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

.empty-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-4);
  padding: var(--s-5) var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.empty-title { color: var(--c-text); font-size: 30rpx; font-weight: 500; }
.empty-copy { color: var(--c-text-2); font-size: 24rpx; line-height: 1.65; }
.empty-btn {
  align-self: flex-start;
  display: flex;
  align-items: center;
  height: 80rpx;
  margin-top: var(--s-1);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 26rpx;
  font-weight: 500;
}

.search-row { position: relative; flex: 0 0 auto; margin-top: var(--s-3); }
.search-input {
  height: var(--touch-min);
  padding: 0 120rpx 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 27rpx;
  box-sizing: border-box;
}
:deep(.search-placeholder) { color: var(--c-text-3); }
.clear-search {
  position: absolute;
  right: var(--s-3);
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-1);
  color: var(--c-primary);
  font-size: 24rpx;
}

/* 左右分栏：左边分类固定宽度，右边菜谱列表吃掉剩余空间 */
.menu-layout { display: flex; gap: var(--s-2); flex: 1; min-height: 0; margin-top: var(--s-3); }
.category-sidebar { flex: 0 0 176rpx; width: 176rpx; height: 100%; }
.category-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-1);
  min-height: var(--touch-min);
  margin-bottom: var(--s-1);
  padding: 0 var(--s-2);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
}
/* 选中态：底色 + 边框 + 文字一起变，三重强调。
   在小屏上单靠换个浅底色，用户不容易看出当前选的是哪个 */
.category-button.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
}
.category-name { color: var(--c-text-2); font-size: 25rpx; }
.category-button.active .category-name { color: var(--c-primary); font-weight: 500; }
.category-count { color: var(--c-text-3); font-size: 21rpx; }
.category-button.active .category-count { color: var(--c-primary); }

.recipe-area { flex: 1; min-width: 0; height: 100%; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; padding: 4rpx 4rpx var(--s-2); }
.section-title { color: var(--c-text); font-size: 27rpx; font-weight: 500; }
.section-count { color: var(--c-text-3); font-size: 22rpx; }

.recipe-card {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 136rpx;
  margin-bottom: var(--s-2);
  padding: var(--s-2);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.recipe-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.recipe-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 29rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recipe-desc {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 23rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recipe-meta { color: var(--c-text-3); font-size: 21rpx; }
.recipe-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 36rpx; line-height: 1; }

/* 有图的菜显示 96rpx 缩略图，位置就是当年分类色块的位置 */
.recipe-photo {
  flex: 0 0 auto;
  width: 96rpx;
  height: 96rpx;
  border-radius: var(--r-sm);
  border: 2rpx solid var(--c-border);
  background: var(--c-muted);
}

/* 收藏星标：做成一个 88rpx 的命中区（手指大小），图形本身只有 40rpx——
   星星那么小的图标，命中区不放大根本点不准 */
.fav-star {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--touch-min);
  height: var(--touch-min);
  margin-right: calc(-1 * var(--s-2));
}
.fav-star-img { width: 40rpx; height: 40rpx; }

.content-state {
  padding: 60rpx var(--s-3);
  color: var(--c-text-2);
  font-size: 24rpx;
  line-height: 1.7;
  text-align: center;
}
/* 给底部 tabBar 留出空间，不然最后一张卡片会被盖住 */
.bottom-space { height: 120rpx; }
</style>
