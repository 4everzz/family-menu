<template>
  <view class="cart-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <!-- 一个家庭组都没有：这里帮不上忙，直接指路 -->
    <view v-else-if="!spaceId" class="empty-card">
      <text class="empty-title">还没有家庭组</text>
      <text class="empty-copy">
        点单是给家里用的。先去「我的 → 设置 → 切换家庭」创建一个家庭组，再回来点菜。
      </text>
      <view class="empty-btn" hover-class="tap" @click="goSettings">前往设置</view>
    </view>

    <!-- 购物车是空的：这不是错误，用引导而不是报错的口吻 -->
    <view v-else-if="!items.length" class="empty-card">
      <text class="empty-title">还没有选菜</text>
      <text class="empty-copy">
        去菜单里挑几道想吃的菜，点每道菜右边的「+」加进来，攒够了一起提交。
      </text>
      <view class="empty-btn" hover-class="tap" @click="goMenu">去菜单选菜</view>
    </view>

    <template v-else>
      <view class="page-head">
        <text class="page-title">点单</text>
        <text class="page-subtitle">{{ spaceName }}</text>
      </view>

      <view class="list-head">
        <text class="list-title">已选 {{ items.length }} 道菜</text>
        <text class="clear-all" hover-class="tap" @click="clearAll">清空</text>
      </view>

      <!-- 已选菜品。刻意没有单价/合计——家里的菜不标价，这单也不需要付款 -->
      <view class="dish-list">
        <view v-for="item in items" :key="cartKey(item)" class="dish-row">
          <view class="dish-copy">
            <text class="dish-name">{{ item.dishName }}</text>
            <!-- 辣度：同一道菜选了两种辣度会是两行，这行小字是区分二者的唯一依据 -->
            <text v-if="item.spice" class="dish-spice">{{ item.spice }}</text>
          </view>

          <!--
            数量步进器。减号到底（减到 0）就等同于把这道菜移出去，
            符合用户"一路点减号"的直觉，不用再去按旁边的删除。
          -->
          <view class="stepper">
            <view class="step-btn" hover-class="tap" @click="changeQuantity(item, item.quantity - 1)">
              -</view
            >
            <text class="step-value">{{ item.quantity }}</text>
            <view class="step-btn" hover-class="tap" @click="changeQuantity(item, item.quantity + 1)">
              +</view
            >
          </view>

          <text class="dish-remove" hover-class="tap" @click="removeItem(item)">删除</text>
        </view>
      </view>

      <view class="form-group">
        <text class="field-label">备注（可不填）</text>
        <textarea
          v-model="remark"
          class="field textarea"
          :disabled="submitting"
          :maxlength="REMARK_MAX_LENGTH"
          placeholder="例如：少辣、不要香菜"
          placeholder-class="field-placeholder"
        />
      </view>

      <!-- 底部留白：给固定的提交栏让位，否则最后一项会被压住 -->
      <view class="bottom-space" />
    </template>

    <!-- 提交栏：固定在底部，随时能提交，不用滚到最下面 -->
    <view v-if="spaceId && items.length" class="submit-bar">
      <view class="submit-summary">
        <text class="summary-main">共 {{ totalQuantity }} 份</text>
        <text class="summary-sub">{{ items.length }} 道菜</text>
      </view>
      <view
        class="submit-btn"
        :class="{ disabled: submitting }"
        hover-class="tap"
        @click="submit"
      >{{ submitting ? '提交中…' : '提交点单' }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
/**
 * 点单购物车页。
 *
 * 场景是**家里来客人点单**：客人翻菜单 → 选菜 → 提交，**不需要付款**。
 * 所以这一页刻意没有任何金额相关的东西：没有单价、没有合计、没有结算、没有支付。
 * 家庭做饭不是买卖，"这单要做什么菜"才是这个场景真正关心的。
 *
 * 界面骨架沿用了旧商家版的购物车（数量加减、备注、提交），
 * 但**数据层是新写的**：旧那套调的是微信云函数，在 App 上直接抛错。
 * 现在走 services/order.ts → 自己的 FastAPI 后端。
 *
 * 购物车内容存在本机（utils/dish-cart.ts），不是每加一道菜就写后端：
 * 客人翻菜单时会反复加减，攒够了一起提交才有意义。
 *
 * 未登录 / 没有家庭组时不报错，而是给出明确的下一步（去登录、去设置）——
 * 报错只说"哪里不对"，引导才说"该怎么做"。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import { createOrder } from '../../services/order';
import { cartKey, clearCart, getCart, removeDish, setQuantity } from '../../utils/dish-cart';
import type { CartItem } from '../../utils/dish-cart';
import { showError } from '../../utils/format';
import { getCurrentSpaceId, getCurrentSpaceName, resolveCurrentSpace } from '../../utils/space-context';
import { PRIMARY } from '../../utils/theme';

/** 备注长度上限要与后端保持一致，见 backend/app/models/dish_order.py */
const REMARK_MAX_LENGTH = 200;

const spaceId = ref('');
const spaceName = ref('');
const items = ref<CartItem[]>([]);
const remark = ref('');
const loading = ref(true);
const submitting = ref(false);

/** 总份数：浮在提交栏上，用户提交前能一眼核对 */
const totalQuantity = computed(() => items.value.reduce((sum, item) => sum + item.quantity, 0));

/**
 * 读取购物车与当前家庭组。
 *
 * 每次进页面都重算：用户可能刚从菜单页加了菜回来，也可能在设置里换了家庭组。
 * 换家庭组后购物车会显示为空——那是刻意的，见 utils/dish-cart.ts 的说明。
 */
async function load(): Promise<void> {
  try {
    await ensureLogin();
    await resolveCurrentSpace();
    spaceId.value = getCurrentSpaceId();
    spaceName.value = getCurrentSpaceName();
    items.value = getCart(spaceId.value);
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

/**
 * 改某一行的份数。
 * 减到 0 时 setQuantity 会自动把这一行移出去，这里不用额外判断。
 *
 * 注意定位用的是 cartKey(item) 而不是 recipeId：
 * 同一道菜选了两种辣度是两行，只按 recipeId 找会改错行。
 */
function changeQuantity(item: CartItem, next: number): void {
  try {
    items.value = setQuantity(spaceId.value, cartKey(item), next);
  } catch (error) {
    // 只有超出单道菜上限时才会走到这里
    showError(error);
  }
}

/** 把一行移出购物车 */
function removeItem(item: CartItem): void {
  items.value = removeDish(spaceId.value, cartKey(item));
}

/**
 * 清空购物车。
 *
 * 要二次确认：点了好几道菜之后一次点错全没了，重来很烦；
 * 而这些菜是本地状态，清掉就真没了（服务端没有备份可恢复）。
 */
function clearAll(): void {
  uni.showModal({
    title: '清空已选的菜',
    content: `已选的 ${items.value.length} 道菜会被全部移除。这个操作不能撤销。`,
    confirmText: '清空',
    confirmColor: PRIMARY,
    success: (res) => {
      if (!res.confirm) return;
      clearCart();
      items.value = [];
    },
  });
}

/**
 * 提交点单。
 *
 * 成功后才清空购物车——反过来的话，提交失败或网络超时会导致"菜没了但单也没提交成"，
 * 用户得从头再选一遍。
 */
async function submit(): Promise<void> {
  if (submitting.value) return;

  if (!items.value.length) {
    uni.showToast({ title: '还没有选菜', icon: 'none' });
    return;
  }

  submitting.value = true;
  try {
    await createOrder(spaceId.value, {
      // 不再收集"这单是谁点的"（用户明确要求去掉）。
      // 后端 guest_name 字段仍然保留，将来真需要时能直接用，现在一律空着。
      guestName: '',
      remark: remark.value,
      items: items.value.map((item) => ({
        recipeId: item.recipeId,
        quantity: item.quantity,
        spice: item.spice,
      })),
    });

    clearCart();
    items.value = [];
    uni.showToast({ title: '下单成功', icon: 'success' });
    // 下单完成后回菜单页。
    // 购物车这时已经空了，把用户留在一个空购物车上，等于逼他自己按返回——
    // 而他的下一件事本来就是"接着点菜"或"看看菜单"。
    goMenu();
  } catch (error) {
    showError(error);
  } finally {
    submitting.value = false;
  }
}

/**
 * 回菜单页。两个地方都用它：空购物车上的「去菜单选菜」，以及**提交成功之后**。
 *
 * 正常路径是从菜单页 navigateTo 进来的，返回即可；
 * 但如果这一页是页面栈里的第一个（比如被 reLaunch 进来），返回会失败，
 * 那就切到菜单标签页兜底——总之不能让"去选菜"变成一个点了没反应的按钮。
 */
function goMenu(): void {
  if (getCurrentPages().length > 1) {
    uni.navigateBack();
  } else {
    uni.switchTab({ url: '/pages/menu/index' });
  }
}

/** 去设置页（创建或加入家庭组） */
function goSettings(): void {
  uni.navigateTo({ url: '/pages/settings/index' });
}

onShow(load);
</script>

<style scoped>
.cart-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) 0;
  box-sizing: border-box;
}

.tip { display: block; margin-top: var(--s-5); color: var(--c-text-3); font-size: 24rpx; text-align: center; }

.page-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--s-3);
}
.page-title { color: var(--c-text); font-size: 40rpx; font-weight: 500; }
.page-subtitle { flex: 0 0 auto; color: var(--c-text-2); font-size: 23rpx; }

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

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--s-3);
  padding: 0 var(--s-1) var(--s-2);
}
.list-title { color: var(--c-text-2); font-size: 24rpx; }
/* 清空是破坏性动作，用危险色提示，但字号克制——它不是这页的主要动线 */
.clear-all {
  display: flex;
  align-items: center;
  min-height: var(--touch-min);
  padding-left: var(--s-2);
  color: var(--c-danger-text);
  font-size: 24rpx;
}

.dish-list {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.dish-row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 128rpx;
  padding: 0 var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.dish-row:last-child { border-bottom: none; }
.dish-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.dish-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 29rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 辣度用次要色：它是菜名的补充信息，不该和菜名抢注意力 */
.dish-spice { color: var(--c-text-2); font-size: 23rpx; }

/* 步进器：两个按钮各 88rpx（规范下限）。中间留 16rpx 而不是 8rpx——
   加减是方向相反的两个操作，挨太近容易点错，而点错的代价是"数量变了" */
.stepper {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.step-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: var(--touch-min);
  height: var(--touch-min);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 34rpx;
  line-height: 1;
}
.step-value {
  min-width: 56rpx;
  color: var(--c-text);
  font-size: 28rpx;
  font-weight: 500;
  text-align: center;
}

.dish-remove {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding-left: var(--s-2);
  color: var(--c-danger-text);
  font-size: 24rpx;
}

.form-group { display: flex; flex-direction: column; gap: var(--s-2); margin-top: var(--s-4); }
.field-label { color: var(--c-text-2); font-size: 24rpx; }
.field {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 27rpx;
  box-sizing: border-box;
}
/* 备注要能写两句，所以给固定高度而不是单行高度；
   textarea 在部分端上默认带自己的内边距，这里统一压掉保证和输入框对齐 */
.textarea {
  height: 160rpx;
  padding: var(--s-2) var(--s-3);
  line-height: 1.6;
}
:deep(.field-placeholder) { color: var(--c-text-3); }
.field-tip { color: var(--c-text-3); font-size: 22rpx; line-height: 1.6; }

/* 给固定提交栏让位 */
.bottom-space { height: 200rpx; }

/* 提交栏：固定底部，让用户随时能提交，不用滚到最后。
   padding-bottom 里加上安全区，全面屏手机上按钮才不会被手势条压住 */
.submit-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  padding: var(--s-2) var(--s-3);
  padding-bottom: calc(var(--s-2) + env(safe-area-inset-bottom));
  border-top: 2rpx solid var(--c-border);
  background: var(--c-surface);
}
.submit-summary { min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.summary-main { color: var(--c-text); font-size: 30rpx; font-weight: 500; }
.summary-sub { color: var(--c-text-3); font-size: 22rpx; }
.submit-btn {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 280rpx;
  height: var(--touch-min);
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 29rpx;
  font-weight: 500;
}
/* 禁用态用更浅的底色 + 不透明文字，而不是降低透明度——
   降透明度会让文字一起变淡，看起来像"加载中"而不是"不能用" */
.submit-btn.disabled { background: var(--c-disabled); color: #fff; }
</style>
