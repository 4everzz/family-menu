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

    <view v-else-if="!authenticated" class="empty-card">
      <text class="empty-title">登录后查看家庭菜单</text>
      <text class="empty-copy">
        登录或注册后即可创建/加入家庭组，和家人一起管理菜谱、冰箱与点单。
      </text>
      <view class="empty-btn" hover-class="tap" @click="goLogin">登录 / 注册</view>
    </view>

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
          type="text"
          class="search-input"
          placeholder="搜索菜名或简介"
          placeholder-class="search-placeholder"
        />
        <text v-if="keyword" class="clear-search" hover-class="tap" @click="keyword = ''">清除</text>
      </view>

      <view class="menu-layout">
        <!-- 分类侧栏：条目 = 全部 + 这个家的分类，顺序完全照用后端 -->
        <view class="category-sidebar">
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
        </view>

        <view class="recipe-area">
          <view class="section-head">
            <text class="section-title">{{ activeCategoryName }}</text>
            <text class="section-count">{{ filtered.length }} 道菜</text>
          </view>

          <view v-if="filtered.length" class="recipe-list">
            <view v-for="item in filtered" :key="item.id" class="recipe-card" hover-class="tap" @click="openDetail(item)">
              <!--
                菜品视觉块（对照旧小程序版的 .dish-visual）。
                有照片就显示照片；没照片时在**分类色底**上显示**菜名首字**。

                为什么不干脆留空？因为一整列空白卡片根本认不出是哪道菜，
                看着还像"功能没做完"。给个带颜色的首字，既能分辨类型又好辨认。
              -->
              <view class="dish-visual" :style="{ background: categoryTint(item) }">
                <image
                  v-if="item.imageUrl"
                  class="dish-photo"
                  :src="resolveFileUrl(item.imageUrl)"
                  mode="aspectFill"
                />
                <text v-else class="dish-initial">{{ item.name.slice(0, 1) }}</text>
              </view>

              <view class="recipe-copy">
                <text class="recipe-name">{{ item.name }}</text>
                <!--
                  没写简介就**整行不显示**（用户要求）。
                  原来固定显示一句"还没写简介"，等于每张卡片都挂一句一样的话：
                  既吵，又让人以为这菜谱是半成品。
                -->
                <text v-if="item.description" class="recipe-desc">{{ item.description }}</text>
                <!-- 只显示分类。不显示"谁加的"（用户要求）——
                     家里几个人一起维护菜谱，标了也没人看，反而占地方 -->
                <text class="recipe-meta">{{ item.categoryName }}</text>
              </view>

              <!--
                「今天不做」的菜：显示标签、不给加。
                注意它**仍然留在菜单里**——直接藏起来的话，用户会以为这道菜被删了。
              -->
              <text v-if="item.isSoldOut" class="soldout-label">已售罄</text>

              <!--
                加入点单：同样必须 @click.stop，否则会顺手把详情页也打开。
                已加过的菜显示份数而不是加号，用户一眼就知道"这道菜我点过了"。
              -->
              <view v-else class="dish-stepper" @click.stop>
                <view
                  v-if="cartQuantityOf(item.id) > 0"
                  class="stepper-btn secondary"
                  hover-class="tap"
                  @click.stop="onDecreaseTap(item)"
                >
                  <text class="stepper-icon">−</text>
                </view>
                <text v-if="cartQuantityOf(item.id) > 0" class="stepper-qty">{{ cartQuantityOf(item.id) }}</text>
                <view class="stepper-btn" hover-class="tap" @click.stop="onAddTap(item)">
                  <text class="stepper-icon">+</text>
                </view>
              </view>
            </view>
          </view>

          <view v-else class="content-state">
            <template v-if="recipes.length">没有找到相关菜谱</template>
            <template v-else-if="!categories.length">
              这个家还没有分类。先去「我的 → 菜单管理 → 分类管理」建一个，才能添加菜谱。
            </template>
            <template v-else>这个家还没有菜谱。</template>
          </view>

          <view class="bottom-space" :class="{ 'with-fab': cartTotal > 0 }" />
        </view>
      </view>
    </template>

    <!--
      底部购物车栏。
      结构和尺寸对照小程序版（miniprogram/pages/menu/index.wxml 的 .cart-bar）：
      通栏药丸 + 左侧购物车图标（纯 CSS 画的篮子 + 份数角标）+ 中间"已选几道" + 右侧实心按钮。
      刻意不显示金额——家里的菜不标价，点了也不付钱。
    -->
    <view v-if="cartTotal > 0" class="cart-bar">
      <view class="cart-bar-main" hover-class="tap" @click="goCart">
        <view class="cart-icon">
          <view class="cart-icon-basket" />
          <view class="cart-icon-wheel left" />
          <view class="cart-icon-wheel right" />
          <text class="cart-icon-badge">{{ cartTotal }}</text>
        </view>
        <view class="cart-bar-summary">
          <text class="cart-bar-count">已选 {{ cartLines }} 道</text>
          <text class="cart-bar-note">共 {{ cartTotal }} 份</text>
        </view>
      </view>
      <view class="cart-bar-selected" hover-class="tap" @click="goCart">去提交</view>
    </view>

    <!--
      辣度选择弹窗（对照旧小程序版的 .dish-modal）。
      只在"这道菜设了辣度档位"时才弹——汤、饮品那类不问辣度的菜，
      点加号就直接加进去了，不该为了一道不需要选的菜多弹一次窗。

      默认选中的是这道菜的默认辣度，所以绝大多数情况下用户直接点"加进去"就行了。
    -->
    <view v-if="spiceDialogDish" class="spice-mask" @click="closeSpiceDialog">
      <view class="spice-dialog" @click.stop>
        <text class="spice-title">{{ spiceDialogDish.name }}</text>
        <text class="spice-hint">选个辣度再加进点单</text>

        <view class="spice-options">
          <view
            v-for="level in spiceDialogDish.spiceOptions"
            :key="level"
            class="spice-option"
            :class="{ active: chosenSpice === level }"
            hover-class="tap"
            @click="chosenSpice = level"
          >{{ level }}</view>
        </view>

        <view class="spice-actions">
          <view class="spice-cancel" hover-class="tap" @click="closeSpiceDialog">取消</view>
          <view class="spice-confirm" hover-class="tap" @click="confirmSpice">加进点单</view>
        </view>
      </view>
    </view>
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
 *   旧的商家代码（扫码进店 / 订单 / 商家登录）已在转型清理时一并删除，
 *   仓库里现在只剩家庭版这一套代码。
 *
 *   2026-09-15：这一页加回了「加入点单」（每张卡片右侧的 +，右下角是购物车浮标）。
 *   它和当初删掉的那个购物车不是一回事——那个是"扫码进店 → 挑菜 → 结算下单"，
 *   带价格和订单；现在是"家里来客人时，把想吃的菜攒起来一起提交"，没有价格也不用付款。
 *   加菜只是存在本机的一段临时选择（utils/dish-cart.ts），**不改动任何家庭数据**，
 *   所以和下面这条"这一页只读"的原则并不冲突。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { LOGIN_PATH } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { resolveFileUrl } from '../../services/http';
import { fetchRecipes } from '../../services/recipe';
import type { Recipe } from '../../services/recipe';
import { addDish, decreaseDish, getCart } from '../../utils/dish-cart';
import type { CartItem } from '../../utils/dish-cart';
import { showError } from '../../utils/format';
import { getCurrentSpaceId, getCurrentSpaceName, resolveCurrentSpace } from '../../utils/space-context';
import { hasValidToken } from '../../utils/token';

const spaceId = ref('');
const spaceName = ref('');
const authenticated = ref(false);
const categories = ref<Category[]>([]);
const recipes = ref<Recipe[]>([]);
/** 当前选中的分类 ID。空字符串代表「全部」，不是后端给的真实分类 */
const activeCategoryId = ref('');
const keyword = ref('');
const loading = ref(true);
const errorMessage = ref('');
/** 是否已成功加载过一次：用来区分「首次进入显示加载中」和「从别处回来时静默刷新」 */
const loadedOnce = ref(false);

/**
 * 点单购物车（本地状态，存在本机，不在后端）。
 *
 * 为什么放在本地而不是每加一道菜就往后端写一条？
 *   客人翻菜单时会反复加减，每一步都发请求既慢又会产生一堆半成品数据；
 *   等他点够了一起提交，"这单要做什么"才是这个场景真正关心的东西。
 *   代价是换设备就没了——对这个场景完全可以接受。
 */
const cartItems = ref<CartItem[]>([]);


/** 当前分类的名字，显示在右侧列表的标题上 */
const activeCategoryName = computed(() => {
  if (!activeCategoryId.value) return '全部';
  return categories.value.find((item) => item.id === activeCategoryId.value)?.name || '全部';
});

/** 购物车总份数，显示在底部购物车栏的角标上 */
const cartTotal = computed(() =>
  cartItems.value.reduce((sum, item) => sum + item.quantity, 0),
);

/** 选了**几道菜**。和"几份"是两个数：3 道菜各 2 份 = 3 道 / 6 份 */
const cartLines = computed(() => cartItems.value.length);

/**
 * 「菜谱 ID → 已点份数」的查找表。
 *
 * 卡片上要显示"这道菜我加了几份"。如果直接在模板里写
 * `cartItems.find(...)`，列表里每张卡片每次渲染都要遍历一遍购物车；
 * 预先算成 Map 之后是 O(1)，模板也好读。
 *
 * ⚠️ 同一道菜选了两种辣度时购物车里是两行（"一份微辣、一份特辣"），
 * 所以这里是**按菜谱 ID 累加**，卡片上显示的是这道菜的总份数。
 */
const cartQuantityMap = computed(() => {
  const map = new Map<string, number>();
  for (const item of cartItems.value) {
    map.set(item.recipeId, (map.get(item.recipeId) || 0) + item.quantity);
  }
  return map;
});

/** 查某道菜在购物车里的份数（没加过就是 0） */
function cartQuantityOf(recipeId: string): number {
  return cartQuantityMap.value.get(recipeId) || 0;
}

/** 从本机缓存重新读一次购物车（进页面、切换家庭组后都要读） */
function refreshCart(): void {
  cartItems.value = getCart(spaceId.value);
}

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

/**
 * 加载菜谱。
 *
 * 每次进入页面都会重新拉一次，因为可能在别处改了数据（比如刚从菜品管理页返回）。
 * 第二次起不显示「加载中」，直接用旧内容顶着，拉回来再替换——避免页面闪一下。
 */
async function load(): Promise<void> {
  loading.value = !loadedOnce.value;
  errorMessage.value = '';
  authenticated.value = hasValidToken();

  // 未登录时仍让菜单首页正常呈现，不在 Tab 页 onShow 阶段自动跳转。
  // 需要账号的功能由用户主动点击后再进入登录页，避免启动阶段跳转造成空白。
  if (!authenticated.value) {
    spaceId.value = '';
    spaceName.value = '';
    categories.value = [];
    recipes.value = [];
    loadedOnce.value = true;
    loading.value = false;
    refreshCart();
    return;
  }

  try {
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
    // 每次进页面都重读一次购物车：用户可能刚在购物车页删了菜、或者提交后清空了，
    // 而这一页的浮标和卡片上的份数都得跟着变
    refreshCart();
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

/** 未登录首页上的明确入口；登录成功后登录页会返回本菜单 Tab。 */
function goLogin(): void {
  uni.navigateTo({ url: LOGIN_PATH });
}

/** 打开菜谱详情（只读）。要改的话去「我的 → 菜单管理 → 菜品管理」 */
function openDetail(item: Recipe): void {
  uni.navigateTo({ url: `/pages/recipe/detail?id=${item.id}` });
}

/**
 * 分类底色。
 *
 * 没上传照片的菜用「分类色底 + 菜名首字」占位，颜色从这里来：
 * 按分类在清单里的**位置**轮着取四个设计令牌里的浅底。
 * 用位置而不是分类 ID 取模，是因为 ID 是自增的、间隔很大，
 * 取模之后颜色会挤在一两个色上，看不出"按类型区分"的效果。
 */
const CATEGORY_TINTS = [
  'var(--c-tint-clay)',
  'var(--c-tint-sand)',
  'var(--c-tint-sage)',
  'var(--c-tint-stone)',
];

function categoryTint(item: Recipe): string {
  const index = categories.value.findIndex((category) => category.id === item.categoryId);
  return CATEGORY_TINTS[(index < 0 ? 0 : index) % CATEGORY_TINTS.length];
}

/** 正在选辣度的那道菜；null 表示弹窗没打开 */
const spiceDialogDish = ref<Recipe | null>(null);
/** 弹窗里当前选中的辣度 */
const chosenSpice = ref('');

/**
 * 点「+」。
 *
 * 不问辣度的菜直接加进去；设了辣度档位的先弹出来让用户选——
 * 这是旧小程序版的交互，家里几个人口味不一样时全靠它。
 */
function onAddTap(item: Recipe): void {
  if (item.isSoldOut) return;

  if (!item.spiceOptions.length) {
    doAdd(item, '');
    return;
  }

  // 默认选中这道菜的默认辣度，所以多数时候用户直接点「加进点单」就行了
  chosenSpice.value = item.defaultSpice || item.spiceOptions[0];
  spiceDialogDish.value = item;
}

/**
 * 点卡片上的「−」。
 *
 * 从这道菜里减一份。因为辣度可能让同一道菜分成多行，
 * 具体减哪一行交给 dish-cart.ts 按"默认辣度优先"的规则处理。
 */
function onDecreaseTap(item: Recipe): void {
  cartItems.value = decreaseDish(spaceId.value, item.id, item.defaultSpice || '');
}

/** 关掉辣度弹窗（点遮罩或取消） */
function closeSpiceDialog(): void {
  spiceDialogDish.value = null;
}

/** 弹窗里点「加进点单」 */
function confirmSpice(): void {
  const dish = spiceDialogDish.value;
  if (!dish) return;
  doAdd(dish, chosenSpice.value);
  spiceDialogDish.value = null;
}

/**
 * 真正写进购物车。
 *
 * 这里**不校验**"我是不是创建人"之类的权限——因为点单是"提需求"，
 * 任何家庭成员都能做（和改菜单不一样）。真正的拦截在后端。
 */
function doAdd(item: Recipe, spice: string): void {
  try {
    cartItems.value = addDish(spaceId.value, item.id, item.name, spice);
    // 加菜是高频操作，给一个短提示就行，不能打断翻菜单的节奏。
    // 带辣度时把辣度一并报出来，用户才知道自己刚加的是哪一份
    const suffix = spice ? `（${spice}）` : '';
    uni.showToast({ title: `已加入「${item.name}」${suffix}`, icon: 'none' });
  } catch (error) {
    // 只有超出上限时才会走到这里（消息是中文的，可直接展示）
    showError(error);
  }
}

/** 去购物车页（提交点单） */
function goCart(): void {
  uni.navigateTo({ url: '/pages/cart/index' });
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
  height: var(--touch-min);
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
  height: var(--touch-min);
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
/* 分类侧栏与菜谱区原本用 scroll-view 做区域滚动；它们和筛选条一样，
   都处在「loading 切换导致整块重挂载」的结构里，scroll-view 在重挂载时会写
   scrollTop/scrollLeft 而节点引用为 null，抛 "of null" 异常。
   这两个容器有固定高度（height:100%）且不需 scroll 事件，改用原生 CSS
   overflow-y:auto 滚动，彻底规避该框架问题。 */
/* 分类侧栏宽度 176rpx → 120rpx（2026-09-19 用户要求：缩到原来的 2/3 左右）。
   省下的 56rpx 全部让给菜谱卡片——卡片里要塞缩略图、菜名、简介和步进器，一直偏挤。
   ⚠️ 变窄之后「名字 + 数量」横排就放不下了（4 个字的分类名会被挤成两截），
      所以内部改成**上下两行居中**：名字在上、数量在下，任何长度的分类名都能容下。 */
.category-sidebar { flex: 0 0 120rpx; width: 120rpx; height: 100%; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.category-button {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2rpx;
  min-height: var(--touch-min);
  margin-bottom: var(--s-1);
  padding: 10rpx 6rpx;
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  text-align: center;
  box-sizing: border-box;
}
/* 选中态：底色 + 边框 + 文字一起变，三重强调。
   在小屏上单靠换个浅底色，用户不容易看出当前选的是哪个 */
.category-button.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
}
.category-name { color: var(--c-text-2); font-size: 24rpx; line-height: 1.2; word-break: break-all; }
.category-button.active .category-name { color: var(--c-primary); font-weight: 500; }
.category-count { color: var(--c-text-3); font-size: 20rpx; }
.category-button.active .category-count { color: var(--c-primary); }

.recipe-area { flex: 1; min-width: 0; height: 100%; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; padding: 4rpx 4rpx var(--s-2); }
.section-title { color: var(--c-text); font-size: 27rpx; font-weight: 500; }
.section-count { color: var(--c-text-3); font-size: 22rpx; }

/* 卡片高度 176rpx → 208rpx（2026-09-19）：
   步进器缩小之后右侧空出一截，把省下的"视觉重量"换成高度——
   卡片更从容，缩略图也更大，翻菜谱时更好认。 */
.recipe-card {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 208rpx;
  margin-bottom: var(--s-2);
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
.recipe-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
/* 菜名允许折两行：卡片左侧被视觉块占掉之后，一行放不下「冬瓜排骨汤」这种名字，
   直接截断会让人分不清是哪道菜 */
.recipe-name {
  display: -webkit-box;
  overflow: hidden;
  color: var(--c-text);
  font-size: 28rpx;
  font-weight: 500;
  line-height: 1.35;
  text-overflow: ellipsis;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.recipe-desc {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 22rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recipe-meta { color: var(--c-text-3); font-size: 21rpx; }

/* 菜品视觉块（对照旧小程序版的 .dish-visual，那边是 192×144）。
   我们这边的卡片被左侧分类栏挤掉一些宽度，所以取一个正方形。
   有照片就显示照片，没有就在分类色底上显示菜名首字——
   留空的话一整列卡片看着像"功能没做完"，还认不出是哪道菜 */
.dish-visual {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 144rpx;
  height: 144rpx;
  overflow: hidden;
  border-radius: var(--r-sm);
}
.dish-photo { width: 100%; height: 100%; }
/* 首字：用主色，压在四个浅底上都够清楚 */
.dish-initial {
  color: var(--c-primary);
  font-size: 48rpx;
  font-weight: 500;
  line-height: 1;
}

/* 卡片上快速加减：参考小程序菜单页的 .dish-quick-add。
   没加过菜时只显示「+」按钮；加过后显示「− 数量 +」。
   按钮用 64rpx 圆形（和小程序版一致），+ 用实心主色、− 用浅色底。 */
/* ---------- 数量步进器（紧凑版，2026-09-19 缩小）----------
   原来按钮 64rpx、间隔 12rpx、数量位 36rpx，整组 188rpx——
   在卡片里占了近 2/3 的横向空间，把菜名挤得只剩一行半。
   现在 56 / 10 / 32 = 164rpx（−13%）。

   ⚠️ 触摸区没有跟着缩到 56rpx：用 ::after 透明层把可点范围撑到约 80rpx。
      视觉变轻、手指仍点得中——这是"看起来小、点起来不小"的标准做法。
      横向只在**外侧**扩（− 往左、+ 往右），中间不重叠，避免加号误触成减号。 */
.dish-stepper {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10rpx;
  height: var(--touch-min);
}
.stepper-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56rpx;
  height: 56rpx;
  border-radius: 28rpx;
  background: var(--c-primary);
  color: #fff;
  box-sizing: border-box;
}
/* 透明扩展层：把点击范围撑到 80×96rpx，但不占布局宽度 */
.stepper-btn::after {
  content: '';
  position: absolute;
  top: -20rpx;
  bottom: -20rpx;
  left: 0;
  right: 0;
}
.stepper-btn.secondary::after { left: -12rpx; right: 0; } /* − 只往左扩 */
.stepper-btn:not(.secondary)::after { left: 0; right: -12rpx; } /* + 只往右扩 */
.stepper-btn.secondary {
  background: var(--c-primary-bg);
  color: var(--c-primary);
}
.stepper-icon {
  font-family: sans-serif;
  font-size: 32rpx;
  font-weight: 700;
  line-height: 1;
}
.stepper-qty {
  min-width: 32rpx;
  color: var(--c-primary);
  font-size: 26rpx;
  font-weight: 700;
  text-align: center;
  white-space: nowrap;
}

/* 「今天不做」标签。
   用提醒色（琥珀）而不是危险色（红）：「今天不做」是随时能恢复的临时状态，
   用红色会让人以为这道菜出问题了、甚至以为要被删掉了 */
.soldout-label {
  flex: 0 0 auto;
  padding: 8rpx 14rpx;
  border-radius: var(--r-sm);
  background: var(--c-warn-bg);
  color: var(--c-warn-text);
  font-size: 22rpx;
  font-weight: 500;
  white-space: nowrap;
}

.content-state {
  padding: 60rpx var(--s-3);
  color: var(--c-text-2);
  font-size: 24rpx;
  line-height: 1.7;
  text-align: center;
}
/* 给底部 tabBar 留出空间，不然最后一张卡片会被盖住 */
.bottom-space { height: 120rpx; }
/* 购物车栏出现时要多留一段，否则最后一张卡片会被它压住半截。
   条形自身 = 96rpx 高 + 与 tabBar 的 8rpx 间距 = 200rpx，这里留 216rpx 稍宽裕 */
.bottom-space.with-fab { height: 216rpx; }

/* ---------- 底部购物车栏 ----------
   对照小程序版的 .cart-bar：
   · 通栏（左右各留 24rpx）、高 96rpx、圆角 48rpx 的药丸形；
   · 深色底托着一个亮色实心按钮，层次一眼分明；
   · 购物车图标不用图片，纯 CSS 拼（篮身 + 提手 + 两个轮子）——
     能用设计令牌控色、任何分辨率都不糊，也不用多带一张图进包。
   bottom 要同时让过 tabBar（约 100rpx）和全面屏手势条（安全区），
   少让一样就会在某个机型上被压住或被挡掉。 */
/* ⚠️ bottom 必须**分平台**写（2026-09-19 踩过）：两端 tabBar 的实现完全不同。
   · H5：tabBar 是 DOM 元素、**盖在页面之上**（实测高 96rpx），页面内容延伸到它底下
         → bottom 要让过整个 tabBar，再加 8rpx 视觉间距 = 104rpx
   · App / 小程序：tabBar 是**原生控件，页面区域本身就不含它**
         → bottom 就是"与 tabBar 的真实间距"，取 40rpx（原 120rpx 的 1/3）
   如果只写一句 104rpx：H5 里贴着 tabBar（对），App 里却会离 tabBar 还有 104rpx——
   用户反馈"手机上没有变化"就是这个原因。 */
/* #ifdef H5 */
.cart-bar { bottom: calc(104rpx + env(safe-area-inset-bottom)); }
/* #endif */
/* #ifndef H5 */
.cart-bar { bottom: calc(40rpx + env(safe-area-inset-bottom)); }
/* #endif */
.cart-bar {
  position: fixed;
  left: var(--s-3);
  right: var(--s-3);
  z-index: 20;
  display: flex;
  align-items: stretch;
  height: 96rpx;
  overflow: hidden;
  border-radius: 48rpx;
  /* 深色底借主文字那个近黑：比纯黑柔和，又不和绿色主色抢注意力 */
  background: var(--c-text);
  color: #fff;
  box-shadow: var(--shadow-float);
}
.cart-bar-main { min-width: 0; flex: 1; display: flex; align-items: stretch; }

/* 购物车图标：92rpx 的固定区域，里面用几个小盒子拼出车形和轮子 */
.cart-icon { position: relative; width: 92rpx; flex: 0 0 92rpx; height: 96rpx; }
.cart-icon-basket {
  position: absolute;
  left: 26rpx;
  top: 31rpx;
  width: 36rpx;
  height: 25rpx;
  border: 4rpx solid #fff;
  border-top: 0;
  border-radius: 0 0 8rpx 8rpx;
  box-sizing: border-box;
}
.cart-icon-basket::before {
  content: '';
  position: absolute;
  left: 2rpx;
  top: -12rpx;
  width: 27rpx;
  height: 12rpx;
  border-top: 4rpx solid #fff;
}
.cart-icon-wheel {
  position: absolute;
  bottom: 24rpx;
  width: 8rpx;
  height: 8rpx;
  border-radius: 50%;
  background: #fff;
}
.cart-icon-wheel.left { left: 31rpx; }
.cart-icon-wheel.right { left: 55rpx; }
/* 角标和右侧按钮都用**主色**而不是"亮一档"：
   亮一档的绿(#16a34a)压白字只有 3.3:1，过不了 4.5:1；
   主色 #15803d 压白字 5.02:1，且与近黑条底的边界对比 3.2:1（UI 边界需 ≥3:1）——两头都达标。 */
.cart-icon-badge {
  position: absolute;
  right: 3rpx;
  top: 11rpx;
  min-width: 30rpx;
  height: 30rpx;
  padding: 0 7rpx;
  border-radius: 16rpx;
  background: var(--c-primary);
  color: #fff;
  font-size: 20rpx;
  font-weight: 700;
  line-height: 30rpx;
  text-align: center;
  box-sizing: border-box;
}

.cart-bar-summary {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-1);
  padding: 0 var(--s-3) 0 var(--s-1);
}
.cart-bar-count { flex: 0 1 auto; font-size: 25rpx; white-space: nowrap; }
.cart-bar-note { flex: 0 0 auto; font-size: 27rpx; font-weight: 500; white-space: nowrap; }

.cart-bar-selected {
  width: 164rpx;
  flex: 0 0 164rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  font-weight: 500;
  white-space: nowrap;
}

/* ---------- 辣度选择弹窗 ----------
   结构对照旧小程序版的 .dish-modal：标题 + 选项网格 + 取消/确定。
   四档排两列，比排成一列短一半，手指也够得着。 */
.spice-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56rpx 44rpx;
  background: rgba(28, 25, 23, 0.48);
  box-sizing: border-box;
}
.spice-dialog {
  width: 100%;
  max-width: 620rpx;
  padding: var(--s-4) var(--s-3);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: 0 16rpx 40rpx rgba(28, 25, 23, 0.22);
  box-sizing: border-box;
}
.spice-title { display: block; color: var(--c-text); font-size: 34rpx; font-weight: 500; }
.spice-hint { display: block; margin-top: 6rpx; color: var(--c-text-2); font-size: 24rpx; }

.spice-options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
.spice-option {
  flex: 0 0 calc(50% - var(--s-1));
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 26rpx;
  box-sizing: border-box;
}
/* 选中态：描边 + 底色 + 字色三重变化，小屏上单靠浅底色看不出选了哪个 */
.spice-option.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-weight: 500;
}

.spice-actions { display: flex; gap: var(--s-2); margin-top: var(--s-4); }
.spice-cancel,
.spice-confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 88rpx;
  border-radius: var(--r-md);
  font-size: 28rpx;
}
.spice-cancel {
  flex: 0 0 200rpx;
  border: 2rpx solid var(--c-border-strong);
  background: var(--c-surface);
  color: var(--c-text-2);
}
.spice-confirm {
  flex: 1;
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}
</style>
