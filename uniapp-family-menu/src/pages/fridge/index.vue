<template>
  <view class="fridge-page">
    <!-- 当前家庭组：在「我的 → 设置 → 切换家庭」里换家后，这里会同步变化 -->
    <view class="space-bar">
      <view class="space-main">
        <text class="space-label">当前家庭</text>
        <text class="space-name">{{ spaceName || '未加入家庭组' }}</text>
      </view>
    </view>

    <!-- 临期横幅：只要有临期/过期就提醒。普通成员也能看到，毕竟是全家要处理的事 -->
    <view v-if="expiringCount > 0" class="alert">
      <view class="alert-icon" aria-label="提醒"></view>
      <text class="alert-text">有 {{ expiringCount }} 件食材临期或已过期，尽快处理</text>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <template v-else>
      <!-- 搜索框：按食材名或备注模糊搜 -->
      <view class="search">
        <input
          v-model="keyword"
          class="search-input"
          placeholder="搜索食材"
          placeholder-class="search-ph"
          confirm-type="search"
        />
      </view>

      <!--
        左右分栏（结构照菜单页）：
        左侧竖排「存放位置」（全部/冷藏/冷冻/常温），右侧是分类药丸 + 食材列表。
        原先两排横向药丸叠在一起显得冗余；存放只有四项，天生适合侧栏。
      -->
      <view class="fridge-layout">
        <view class="storage-sidebar">
          <view
            v-for="s in storages"
            :key="'s-' + s"
            class="storage-button"
            :class="{ active: activeStorage === s }"
            hover-class="tap"
            @click="activeStorage = s"
          >{{ s }}</view>
        </view>

        <view class="fridge-area">
          <view class="filter-scroll">
            <view class="filter-track">
              <view
                v-for="c in categories"
                :key="'c-' + c"
                class="chip"
                :class="{ active: activeCategory === c }"
                hover-class="tap"
                @click="activeCategory = c"
              >{{ c }}</view>
            </view>
          </view>

          <!-- 食材列表 -->
          <view v-if="items.length" class="list">
            <view
              v-for="item in items"
              :key="item.id"
              class="card"
              :class="{ expiring: item.isExpiring, 'has-del': isOwner }"
              hover-class="tap"
              @click="openItem(item)"
            >
              <view class="card-head">
                <text class="card-name">{{ item.name }}</text>
                <text class="card-qty">{{ formatQty(item) }}</text>
              </view>

              <view class="card-tags">
                <text v-if="item.category" class="tag">{{ item.category }}</text>
                <text v-if="item.storage" class="tag tag-storage">{{ item.storage }}</text>
                <text v-if="item.expiryDate" class="tag" :class="expiryTagClass(item)">{{ expiryLabel(item) }}</text>
              </view>

              <text v-if="item.note" class="card-note">{{ item.note }}</text>

              <!-- 删除：仅创建人。普通成员看不到这个按钮，只能浏览 -->
              <view
                v-if="isOwner"
                class="card-del"
                hover-class="tap"
                @click.stop="removeItem(item)"
              >删除</view>
            </view>
          </view>

          <view v-else class="empty">
            <text class="empty-text">这个分类下还没有食材</text>
            <text v-if="isOwner" class="empty-hint">点右下角「添加食材」记一笔</text>
          </view>
        </view>
      </view>
    </template>

    <!-- 添加按钮：仅创建人可看。普通成员没有入口，符合"仅创建人能改冰箱" -->
    <view v-if="isOwner" class="fab" hover-class="tap" @click="goAdd">＋ 添加食材</view>
  </view>
</template>

<script setup lang="ts">
/**
 * 家庭冰箱列表页。
 *
 * 三个要点：
 * 1. 冰箱是家庭共享域，全家人都能看。但**只有创建人能改**——所以添加按钮、
 *    每条的删除按钮都按 isOwner 显示；普通成员进来是纯浏览。
 *    （隐藏只是体验，后端写接口仍会校验创建人，别人绕开界面也改不了。）
 *
 * 2. 临期横幅的计数来自后端 expiring_count，统计的是**整个家庭组**，
 *    不受当前筛选影响——这样顶部提示始终稳定，不会因为切了分类就数字乱跳。
 *
 * 3. 筛选（分类/存放）和搜索都直接传给后端，后端返回的子集就是页面要显示的；
 *    列表本身不做二次过滤，避免和后端计数对不上。
 */

import { ref, watch } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import { fetchFridge, deleteFridgeItem, type FridgeItem } from '../../services/fridge';
import { getCurrentSpace, getCurrentSpaceId, getCurrentSpaceName } from '../../utils/space-context';
import { showError } from '../../utils/format';
import { DANGER } from '../../utils/theme';

const CATEGORIES = ['全部', '蔬菜', '肉蛋', '水产', '调料', '饮品', '其他'];
const STORAGES = ['全部', '冷藏', '冷冻', '常温'];
// 模板里用首字母小写的别名引用，保持和模板变量命名一致
const categories = CATEGORIES;
const storages = STORAGES;

const items = ref<FridgeItem[]>([]);
const expiringCount = ref(0);
const loading = ref(true);
const spaceName = ref('');
const isOwner = ref(false);

const activeCategory = ref('全部');
const activeStorage = ref('全部');
const keyword = ref('');

/** 把筛选条件转成后端要的参数（"全部"表示不过滤） */
function buildQuery(): { category?: string; storage?: string; keyword?: string } {
  const q: { category?: string; storage?: string; keyword?: string } = {};
  if (activeCategory.value !== '全部') q.category = activeCategory.value;
  if (activeStorage.value !== '全部') q.storage = activeStorage.value;
  if (keyword.value.trim()) q.keyword = keyword.value.trim();
  return q;
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    await ensureLogin();
    const spaceId = getCurrentSpaceId();
    spaceName.value = getCurrentSpaceName();
    isOwner.value = getCurrentSpace()?.myRole === 'admin';

    if (!spaceId) {
      showError('还没有选择家庭组');
      items.value = [];
      return;
    }

    const data = await fetchFridge(spaceId, buildQuery());
    items.value = data.items;
    expiringCount.value = data.expiringCount;
  } catch (error) {
    showError(error);
  } finally {
    loading.value = false;
  }
}

onShow(load);

/** 切换筛选条件后立即重新拉取 */
function refetch(): void {
  void load();
}
// 筛选或搜索变化时重新拉取（keyword 用 watch 防抖无所谓，数据量小，直接拉）
watch([activeCategory, activeStorage, keyword], () => refetch());

/** 数量 + 单位，如「10 个」「2 盒」；没单位就只显示数字 */
function formatQty(item: FridgeItem): string {
  const q = Number.isInteger(item.quantity) ? String(item.quantity) : item.quantity.toFixed(1);
  return item.unit ? `${q} ${item.unit}` : q;
}

/** 保质期标签：已过期 / 还有 N 天 / 具体日期 */
function expiryLabel(item: FridgeItem): string {
  if (!item.expiryDate) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const exp = new Date(item.expiryDate.replace(/-/g, '/'));
  const diff = Math.round((exp.getTime() - today.getTime()) / 86400000);
  if (diff < 0) return `已过期 ${-diff} 天`;
  if (diff === 0) return '今天到期';
  if (diff <= 7) return `还有 ${diff} 天`;
  return item.expiryDate;
}

/** 临期标签配色：已过期用危险色，临期用提醒色 */
function expiryTagClass(item: FridgeItem): string {
  if (!item.expiryDate) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const exp = new Date(item.expiryDate.replace(/-/g, '/'));
  const diff = Math.round((exp.getTime() - today.getTime()) / 86400000);
  return diff < 0 ? 'tag-expired' : 'tag-near';
}

/** 点食材卡片：创建人进编辑页，普通成员只浏览（这里普通成员点了没反应，符合权限） */
function openItem(item: FridgeItem): void {
  if (!isOwner.value) return;
  uni.navigateTo({ url: `/pages/fridge/edit?id=${item.id}` });
}

function goAdd(): void {
  if (!isOwner.value) return;
  uni.navigateTo({ url: '/pages/fridge/edit' });
}

/** 删除食材：二次确认，避免手滑删掉家人记的库存 */
function removeItem(item: FridgeItem): void {
  uni.showModal({
    title: '删除食材',
    content: `确定把「${item.name}」从冰箱里删掉吗？删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;
      try {
        await deleteFridgeItem(getCurrentSpaceId(), item.id);
        uni.showToast({ title: '已删除', icon: 'success' });
        await load();
      } catch (error) {
        showError(error);
      }
    },
  });
}
</script>

<style scoped>
.fridge-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: var(--s-4) var(--s-3) 0;
  box-sizing: border-box;
}

.space-bar {
  flex: 0 0 auto;
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

.alert {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
  padding: var(--s-3);
  border-radius: var(--r-md);
  background: var(--c-warn-bg);
  border: 2rpx solid var(--c-warn-border);
}
/* 提醒图标：纯 CSS 矢量三角 + 感叹号，颜色走品牌提醒令牌（微信小程序不支持内联 svg，故用 CSS 画）。
   不用 emoji——emoji 跨平台字体不一致、也拿不到设计令牌颜色。 */
.alert-icon {
  position: relative;
  flex: 0 0 auto;
  width: 30rpx;
  height: 28rpx;
  border-left: 16rpx solid transparent;
  border-right: 16rpx solid transparent;
  border-bottom: 28rpx solid var(--c-warn);
}
.alert-icon::after {
  content: '!';
  position: absolute;
  left: 50%;
  top: 7rpx;
  transform: translateX(-50%);
  color: #fff;
  font-size: 18rpx;
  font-weight: 700;
  line-height: 1;
}
.alert-text { color: var(--c-warn-text); font-size: 24rpx; line-height: 1.5; }

.tip { margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

/* 左右分栏：左侧存放侧栏固定宽度，右侧分类药丸 + 列表吃掉剩余空间（结构照菜单页） */
.fridge-layout { display: flex; gap: var(--s-2); flex: 1; min-height: 0; margin-top: var(--s-3); }
/* 侧栏与列表区用原生 CSS overflow 滚动，不用 scroll-view——
   scroll-view 在 loading 切换重挂载时会写 scrollLeft/scrollTop 而节点引用为 null，
   抛 "of null" 异常（DCloud 老问题，详见菜单页同款注释）。 */
.storage-sidebar { flex: 0 0 176rpx; width: 176rpx; height: 100%; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.storage-button {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--touch-min);
  margin-bottom: var(--s-1);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 25rpx;
}
.storage-button.active {
  border-color: var(--c-primary);
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-weight: 500;
}
.fridge-area {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  /* 底部留出 FAB 的高度，最后一张卡片不被「添加食材」盖住 */
  padding-bottom: 200rpx;
  box-sizing: border-box;
}
/* 分类药丸：横向滚动，多了也不挤 */
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

.search { flex: 0 0 auto; margin-top: var(--s-3); }
.search-input {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 28rpx;
  box-sizing: border-box;
}
.search-ph { color: var(--c-text-3); }

.list { margin-top: var(--s-3); display: flex; flex-direction: column; gap: var(--s-2); }

.card {
  position: relative;
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}
/* 临期卡片：左边一道暖色竖条，扫一眼就知道该优先处理 */
.card.expiring { border-left: 8rpx solid var(--c-warn); }
.card-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-2); }
/* 创建人能看到右上角删除按钮时，给标题行预留右侧空间，避免食材名/数量和删除按钮叠在一起 */
.card.has-del .card-head { padding-right: 120rpx; }
.card-name { color: var(--c-text); font-size: 30rpx; font-weight: 600; }
.card-qty { color: var(--c-text-2); font-size: 26rpx; }
.card-tags { display: flex; flex-wrap: wrap; gap: var(--s-1); margin-top: var(--s-2); }
.tag {
  padding: 4rpx var(--s-2);
  border-radius: var(--r-sm);
  background: var(--c-muted);
  color: var(--c-text-2);
  font-size: 21rpx;
}
.tag-storage { background: var(--c-tint-sage); color: var(--c-sage-text); }
.tag-near { background: var(--c-warn-bg); color: var(--c-warn-text); }
.tag-expired { background: var(--c-danger-bg); color: var(--c-danger-text); }
.card-note {
  display: block;
  margin-top: var(--s-2);
  color: var(--c-text-2);
  font-size: 23rpx;
  line-height: 1.6;
}
.card-del {
  position: absolute;
  top: var(--s-3);
  right: var(--s-3);
  padding: 6rpx var(--s-3);
  border-radius: var(--r-sm);
  color: var(--c-danger);
  font-size: 23rpx;
  background: var(--c-danger-bg);
}

.empty { margin-top: 100rpx; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); }
.empty-text { color: var(--c-text-2); font-size: 27rpx; }
.empty-hint { color: var(--c-text-3); font-size: 23rpx; }

.fab {
  position: fixed;
  right: var(--s-4);
  bottom: calc(var(--s-5) + env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  height: 92rpx;
  padding: 0 var(--s-4);
  border-radius: var(--r-pill);
  background: var(--c-primary);
  color: #fff;
  font-size: 28rpx;
  font-weight: 500;
  box-shadow: var(--shadow-float);
}
</style>
