<template>
  <view class="orders-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="!spaceId" class="empty-card">
      <text class="empty-title">还没有家庭组</text>
      <text class="empty-copy">
        点单是给家里用的。先去「我的 → 设置 → 切换家庭」创建一个家庭组。
      </text>
      <view class="empty-btn" hover-class="tap" @click="goSettings">前往设置</view>
    </view>

    <template v-else>
      <!--
        筛选。默认停在「待处理」——做饭的人最想知道的是"还有哪些没做"，
        而不是翻整本历史。要回顾就切到「已完成」或「全部」。
      -->
      <view class="filter-row">
        <view
          v-for="tab in FILTER_TABS"
          :key="tab.label"
          class="filter-pill"
          :class="{ active: filter === tab.value }"
          hover-class="tap"
          @click="switchFilter(tab.value)"
        >
          <text class="filter-text">{{ tab.label }}</text>
        </view>
      </view>

      <view v-if="errorMessage" class="error-card">
        <text class="error-text">{{ errorMessage }}</text>
        <view class="retry-btn" hover-class="tap" @click="load">重试</view>
      </view>

      <view v-else-if="!orders.length" class="content-state">{{ emptyText }}</view>

      <view v-else class="order-list">
        <view v-for="order in orders" :key="order.id" class="order-card">
          <view class="order-head">
            <text class="order-status" :class="order.status">
              {{ order.status === ORDER_STATUS_DONE ? '已完成' : '待处理' }}
            </text>
            <text class="order-time">{{ formatDateTime(order.createdAt) }}</text>
          </view>

          <!-- 菜名是**下单那一刻的快照**：菜谱后来改名或删掉，这张单依然说得清点了什么 -->
          <view class="order-dishes">
            <view v-for="item in order.items" :key="item.id" class="dish-line">
              <text class="dish-name">{{ item.dishName }}</text>
              <!-- 辣度也是下单时的快照：菜单后来改了档位，这张单显示的仍是当时选的那档 -->
              <text v-if="item.spice" class="dish-spice">{{ item.spice }}</text>
              <text class="dish-qty">×{{ item.quantity }}</text>
            </view>
          </view>

          <view v-if="order.remark" class="order-remark">
            <text class="remark-label">备注</text>
            <text class="remark-text">{{ order.remark }}</text>
          </view>

          <text class="order-meta">{{ orderMeta(order) }}</text>

          <!--
            操作按钮只在 canManage 时出现。这个值由**后端**判定（创建人 或 提交者本人），
            前端不自己算——否则规则一改就会出现"按钮看得到、点下去被拒"。
          -->
          <view v-if="order.canManage" class="order-actions">
            <view class="action-btn" hover-class="tap" @click="toggleStatus(order)">
              {{ order.status === ORDER_STATUS_DONE ? '撤回成待处理' : '标记已完成' }}
            </view>
            <view class="action-btn danger" hover-class="tap" @click="removeOrder(order)">删除</view>
          </view>
        </view>
      </view>

      <view class="bottom-space" />
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 点单记录页（"今天收到什么单、要做什么菜"）。
 *
 * 这是给**做饭的人**看的页面：客人点完单，家里谁负责做饭就照这张单来。
 * 所以默认停在「待处理」，并且把菜名和份数放在最显眼的位置。
 *
 * 权限（和菜单/冰箱刻意不同）：
 *   任何人都能**看**这个家的点单；
 *   但只有**提交者本人**和**创建人**能改状态、删除。
 *   这个判断在后端算好了给前端一个 canManage 字段，前端只管照着显示按钮。
 *
 * 关于"已完成"：
 *   它表达的是"这单做完了 / 结束了"，不是付款或发货状态——
 *   家里的点单不涉及钱，这一点和商家的订单有本质区别。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import {
  ORDER_STATUS_DONE,
  ORDER_STATUS_PENDING,
  deleteOrder,
  fetchOrders,
  updateOrderStatus,
} from '../../services/order';
import type { DishOrder, OrderStatus } from '../../services/order';
import { formatDateTime, showError } from '../../utils/format';
import { getCurrentSpaceId, resolveCurrentSpace } from '../../utils/space-context';
import { DANGER } from '../../utils/theme';

/** 筛选档位。value 为 undefined 表示"不筛选"，也就是全部 */
const FILTER_TABS: Array<{ label: string; value: OrderStatus | undefined }> = [
  { label: '待处理', value: ORDER_STATUS_PENDING },
  { label: '已完成', value: ORDER_STATUS_DONE },
  { label: '全部', value: undefined },
];

const spaceId = ref('');
const orders = ref<DishOrder[]>([]);
const filter = ref<OrderStatus | undefined>(ORDER_STATUS_PENDING);
const loading = ref(true);
const errorMessage = ref('');
/** 是否已成功加载过一次：用来区分"首次进入显示加载中"和"切筛选时静默刷新" */
const loadedOnce = ref(false);

/** 空态文案跟着筛选走：只说"没有数据"会让人以为出错了 */
const emptyText = computed(() => {
  if (filter.value === ORDER_STATUS_PENDING) {
    return '还没有待处理的点单。家里来人时，把想吃的菜加进购物车提交就行。';
  }
  if (filter.value === ORDER_STATUS_DONE) return '还没有已完成的点单。';
  return '这个家还没有点单记录。';
});

/** 卡片底部一行：谁点的 + 一共几份 */
function orderMeta(order: DishOrder): string {
  // 客人借创建人手机点单时，提交者是创建人、客人名字在 guestName 里——
  // 那种情况说"张三 点的"才有用，说"创建人提交的"等于没说
  const who = order.guestName
    ? `${order.guestName} 点的`
    : `${order.createdByName || '家人'} 提交的`;
  return `${who} · 共 ${order.dishCount} 道 / ${order.totalQuantity} 份`;
}

/**
 * 拉取点单列表。
 *
 * 每次进页面都会重新拉：客人刚提交完会跳到这一页（见 pages/cart/index.vue），
 * 不重拉就看不到那张新单。
 */
async function load(): Promise<void> {
  loading.value = !loadedOnce.value;
  errorMessage.value = '';
  try {
    await ensureLogin();
    await resolveCurrentSpace();
    spaceId.value = getCurrentSpaceId();

    if (!spaceId.value) {
      orders.value = [];
      return;
    }

    orders.value = await fetchOrders(spaceId.value, filter.value);
    loadedOnce.value = true;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取点单失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/** 切换筛选：立刻用本地已有的数据过滤不现实（后端只返回了筛选后的子集），所以重新请求 */
function switchFilter(next: OrderStatus | undefined): void {
  if (filter.value === next) return;
  filter.value = next;
  load();
}

/**
 * 改状态：待处理 ⇄ 已完成。
 *
 * 改完重新拉一次列表，而不是就地改这一条：
 * 当前正停在「待处理」时，标成已完成的那张单**本来就不该再出现**，
 * 就地改的话它会以"已完成"的样子赖在待处理列表里，看着很怪。
 */
async function toggleStatus(order: DishOrder): Promise<void> {
  const next = order.status === ORDER_STATUS_DONE ? ORDER_STATUS_PENDING : ORDER_STATUS_DONE;
  try {
    await updateOrderStatus(spaceId.value, order.id, next);
    await load();
    uni.showToast({ title: next === ORDER_STATUS_DONE ? '已标记完成' : '已撤回', icon: 'none' });
  } catch (error) {
    showError(error);
  }
}

/** 删除一张点单。要二次确认——单子删了就没了，也没有"回收站" */
function removeOrder(order: DishOrder): void {
  uni.showModal({
    title: '删除这张点单',
    content: '删掉之后这张单和它点的菜都会消失，不能撤销。',
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (res) => {
      if (!res.confirm) return;
      try {
        await deleteOrder(spaceId.value, order.id);
        await load();
        uni.showToast({ title: '已删除', icon: 'none' });
      } catch (error) {
        showError(error);
      }
    },
  });
}

/** 去设置页（创建或加入家庭组） */
function goSettings(): void {
  uni.navigateTo({ url: '/pages/settings/index' });
}

onShow(load);
</script>

<style scoped>
.orders-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) 0;
  box-sizing: border-box;
}

.tip { display: block; margin-top: var(--s-5); color: var(--c-text-3); font-size: 24rpx; text-align: center; }

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

/* 筛选药丸：选中态用底色 + 文字颜色双重强调，小屏上单靠浅底色看不出选的是哪个 */
.filter-row { display: flex; gap: var(--s-2); }
.filter-pill {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
}
.filter-pill.active { border-color: var(--c-primary); background: var(--c-primary-bg); }
.filter-text { color: var(--c-text-2); font-size: 25rpx; }
.filter-pill.active .filter-text { color: var(--c-primary); font-weight: 500; }

.error-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-danger-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.error-text { color: var(--c-danger); font-size: 27rpx; font-weight: 500; }
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

.content-state {
  padding: 60rpx var(--s-3);
  color: var(--c-text-2);
  font-size: 24rpx;
  line-height: 1.7;
  text-align: center;
}

.order-list { margin-top: var(--s-3); }
.order-card {
  margin-bottom: var(--s-2);
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}

.order-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); }
/* 状态标签：待处理用提醒色（要有人去做），已完成用正向色（做完了） */
.order-status {
  padding: 4rpx var(--s-2);
  border-radius: var(--r-pill);
  font-size: 22rpx;
  font-weight: 500;
}
.order-status.pending { background: var(--c-warn-bg); color: var(--c-warn-text); }
.order-status.done { background: var(--c-accent-bg); color: var(--c-accent); }
.order-time { flex: 0 0 auto; color: var(--c-text-3); font-size: 22rpx; }

/* 菜品清单：这页真正的主角，所以字号给得比元信息大一档 */
.order-dishes {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  margin-top: var(--s-2);
}
.dish-line { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-2); }
.dish-name { min-width: 0; flex: 1; color: var(--c-text); font-size: 29rpx; }
/* 辣度：和菜名同一行，用次要色 + 比菜名小的字，做成"菜名的附注"而不是并列的两项 */
.dish-spice { flex: 0 0 auto; color: var(--c-text-2); font-size: 23rpx; }
.dish-qty { flex: 0 0 auto; color: var(--c-text-2); font-size: 25rpx; }

/* 备注用左侧色条区分：它是"额外信息"，不该和菜名抢注意力，但也不能看不见 */
.order-remark {
  display: flex;
  gap: var(--s-2);
  margin-top: var(--s-2);
  padding-left: var(--s-2);
  border-left: 6rpx solid var(--c-warn-border);
}
.remark-label { flex: 0 0 auto; color: var(--c-warn-text); font-size: 23rpx; }
.remark-text { color: var(--c-text-2); font-size: 23rpx; line-height: 1.6; }

.order-meta {
  display: block;
  margin-top: var(--s-2);
  color: var(--c-text-3);
  font-size: 21rpx;
}

.order-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--s-2);
  margin-top: var(--s-2);
  padding-top: var(--s-2);
  border-top: 2rpx solid var(--c-border);
}
.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 180rpx;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 25rpx;
}
/* 删除是破坏性动作，用危险色描边 + 危险文字，和"标记完成"明确区分开 */
.action-btn.danger { border-color: var(--c-danger-border); color: var(--c-danger-text); }

.bottom-space { height: calc(var(--s-6) + env(safe-area-inset-bottom)); }
</style>
