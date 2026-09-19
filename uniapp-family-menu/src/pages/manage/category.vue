<template>
  <view class="manage-page" :class="{ 'with-bar': selectMode }">
    <view class="page-head">
      <view class="page-head-top">
        <!-- 状态取代标题（2026-09-19）：导航栏已写「分类管理」，页内不重复；
             这里回答"现在有几个分类"，选中时换成已选数 -->
        <text class="page-status">
          {{ selectMode ? `已选 ${pickedIds.length} 个` : `共 ${categories.length} 个分类` }}
        </text>
        <view class="head-actions">
          <!-- 新增：与菜品管理页一致，从列表最下方挪到右上角（那边用户反馈要一直下滑） -->
          <view v-if="!selectMode" class="head-btn primary" hover-class="tap" @click="add">
            新增分类
          </view>
          <!-- 批量删除入口：每行挂一个删除键太臃肿，改成右上角一个入口 -->
          <view v-if="categories.length" class="head-btn" hover-class="tap" @click="toggleSelectMode">
            {{ selectMode ? '取消' : '批量删除' }}
          </view>
        </view>
      </view>
      <!-- 原说明两句话：第一句（"分类是你们家自己的一套，可以随意增删改"）看按钮就懂，删掉；
           第二句是**非显而易见**的机制（改名会连带更新），保留成一行。
           选中模式下的这条规则说明放页面底部的 .page-note 里，那里才是操作发生的地方。 -->
      <text v-if="!selectMode" class="page-desc">
        改名后，这一类下的菜会自动跟着换名字。
      </text>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <view v-if="categories.length" class="list">
        <view
          v-for="item in categories"
          :key="item.id"
          class="row"
          :class="{ picked: isPicked(item.id), locked: selectMode && item.recipeCount > 0 }"
          :hover-class="canPick(item) ? 'tap' : 'none'"
          @click="onRowTap(item)"
        >
          <view v-if="selectMode" class="check" :class="{ on: isPicked(item.id) }" />
          <view class="row-main">
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta">
              {{ item.recipeCount }} 道菜{{ selectMode && item.recipeCount > 0 ? ' · 还有菜，不能删' : '' }}
            </text>
          </view>
          <view v-if="!selectMode" class="row-actions">
            <view class="action" hover-class="tap" @click.stop="rename(item)">改名</view>
          </view>
        </view>
      </view>

      <!-- 一个分类都没有时，空着手给个边框卡片会像"加载坏了"——换成一句说明 + 明确的下一步 -->
      <view v-else class="empty-card">
        <text class="empty-title">还没有分类</text>
        <text class="empty-copy">点右上角「新增分类」建第一个，比如「热菜」「汤」。建好之后，加菜时就能选它了。</text>
      </view>

      <text class="page-note">分类下还有菜的时候不能删除——先把那些菜改到别的分类，再来删。</text>

      <!-- 批量操作栏：固定在底部（本页不是 tabBar 页，bottom:0 就是屏幕底） -->
      <view v-if="selectMode" class="select-bar">
        <view class="select-all" hover-class="tap" @click="toggleAll">
          {{ allPicked ? '取消全选' : '全选' }}
        </view>
        <text class="select-count">已选 {{ pickedIds.length }} 个</text>
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
 * 分类管理页：管理当前家庭组的那一套菜谱分类。
 *
 * 藏在「我的 → 菜单管理」下面，而不是放在菜单页上。
 * 菜单页是每天要用的地方，那里只放"看菜、找菜"；
 * 分类的增删改一个月未必用一次，属于设置类操作，放一起才不会天天占着视线。
 *
 * 关于删除：分类下还有菜时不让删。
 * 如果允许直接删，那些菜就失去了归属——既搜不到也显示不出来，等于凭空消失。
 * 前端在这里先拦一道（为了给出更好的提示），后端还会再拦一次（防止绕过界面直接调接口）。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { createCategory, deleteCategory, fetchCategories, renameCategory } from '../../services/category';
import { getCurrentSpaceId } from '../../utils/space-context';
import { showError } from '../../utils/format';
import { DANGER } from '../../utils/theme';

const spaceId = ref('');
const categories = ref<Category[]>([]);
const loading = ref(true);
const errorMessage = ref('');
/** 操作进行中标记：防止连点重复提交 */
const pending = ref(false);
/** 是否处于批量选择模式 */
const selectMode = ref(false);
/** 已勾选的分类 ID */
const pickedIds = ref<string[]>([]);

/**
 * 能参与批量删除的分类 = 下面没有菜的。
 *
 * 分类下有菜不能删是既有规则（菜会失去归属、等于凭空消失）。
 * 所以批量模式里**这类行根本不给勾**，而不是让用户勾了再被拒——
 * 原来的页面注释写得很对："给了也删不掉，是耍人"。
 */
const selectable = computed(() => categories.value.filter((item) => item.recipeCount === 0));
const allPicked = computed(
  () => selectable.value.length > 0 && selectable.value.every((item) => pickedIds.value.includes(item.id)),
);

async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();
    if (!spaceId.value) throw new Error('还没有选择家庭组');
    categories.value = await fetchCategories(spaceId.value);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/**
 * 新增分类。
 *
 * 用系统弹窗的输入框（editable），而不是自己搭一个弹窗组件——
 * 这里只需要"输入一个名字"，系统弹窗就够了，还自带键盘处理和确认逻辑。
 */
function add(): void {
  if (pending.value) return;
  uni.showModal({
    title: '新增分类',
    editable: true,
    placeholderText: '例如：早餐、夜宵',
    confirmText: '创建',
    success: async (result) => {
      if (!result.confirm) return;
      const name = (result.content || '').trim();
      if (!name) {
        showError('分类名不能为空');
        return;
      }
      pending.value = true;
      uni.showLoading({ title: '创建中' });
      try {
        await createCategory(spaceId.value, name);
        uni.showToast({ title: '已创建', icon: 'success' });
        await load();
      } catch (error) {
        showError(error instanceof Error ? error.message : '创建失败，请重试');
      } finally {
        uni.hideLoading();
        pending.value = false;
      }
    },
  });
}

async function rename(item: Category): Promise<void> {
  if (pending.value) return;
  uni.showModal({
    title: '修改分类名',
    // editable 模式下 content 是输入框的初始内容，也就是把现在的名字预填进去
    content: item.name,
    editable: true,
    placeholderText: '输入新的分类名',
    confirmText: '保存',
    success: async (result) => {
      if (!result.confirm) return;
      const name = (result.content || '').trim();
      if (!name) {
        showError('分类名不能为空');
        return;
      }
      if (name === item.name) return; // 没改，直接当成功处理，不打扰用户
      pending.value = true;
      uni.showLoading({ title: '保存中' });
      try {
        await renameCategory(spaceId.value, item.id, name);
        uni.showToast({ title: '已保存', icon: 'success' });
        await load();
      } catch (error) {
        showError(error instanceof Error ? error.message : '保存失败，请重试');
      } finally {
        uni.hideLoading();
        pending.value = false;
      }
    },
  });
}

/**
 * 批量删除（2026-09-18 改）。
 *
 * 以前每行挂「改名 + 删除」两个键，列表看着很吵。
 * 现在删除收进右上角入口：进选择模式 → 勾选 → 底部删除 → 二次确认（列出所选分类名）。
 * 「改名」留在行内——它是无损操作，点错也没关系，不值得再藏一层。
 *
 * 逐个调删除接口而不是新加批量接口：现有接口本来就带归属与权限校验，复用它少一条路径；
 * 分类一共几个，开销可以忽略。代价是可能"删了一半"，所以失败的收集起来如实汇报。
 */
function toggleSelectMode(): void {
  selectMode.value = !selectMode.value;
  // 进和出都清空，免得下次进来还留着上一轮的勾选
  pickedIds.value = [];
}

function isPicked(id: string): boolean {
  return pickedIds.value.includes(id);
}

/** 这一行现在能不能勾（只跟"有没有菜"有关） */
function canPick(item: Category): boolean {
  return selectMode.value && item.recipeCount === 0;
}

function onRowTap(item: Category): void {
  if (!selectMode.value) return; // 普通模式下这行没有动作（改名是行内按钮）
  if (item.recipeCount > 0) {
    // 不可勾的行点一下就说明原因，别让用户以为点了没反应
    explainLocked(item);
    return;
  }
  pickedIds.value = isPicked(item.id)
    ? pickedIds.value.filter((id) => id !== item.id)
    : [...pickedIds.value, item.id];
}

/**
 * 还有菜的分类为什么不能删。
 * 数量用的是后端返回的 recipeCount（全量口径），不会因为筛选过而算少。
 */
function explainLocked(item: Category): void {
  uni.showModal({
    title: '这个分类还不能删',
    content: `「${item.name}」下还有 ${item.recipeCount} 道菜。请先把这些菜改到别的分类，再来删除这个分类。`,
    showCancel: false,
    confirmText: '知道了',
  });
}

/** 全选 / 取消全选：只作用于"能删的"那些（有菜的分类本来就不给勾） */
function toggleAll(): void {
  pickedIds.value = allPicked.value ? [] : selectable.value.map((item) => item.id);
}

/** 弹窗里列分类名：超过 5 个只列前 5 个 + 共 N 个，否则弹窗会长到看不完 */
function nameList(names: string[]): string {
  const SHOW = 5;
  if (names.length <= SHOW) return names.join('、');
  return `${names.slice(0, SHOW).join('、')} 等 ${names.length} 个分类`;
}

function removeSelected(): void {
  if (pending.value || !pickedIds.value.length) return;
  const targets = selectable.value.filter((item) => isPicked(item.id));
  if (!targets.length) return;

  uni.showModal({
    title: `删除 ${targets.length} 个分类`,
    content: `确定要删除以下分类吗？\n\n${nameList(targets.map((item) => item.name))}\n\n删除后无法恢复。`,
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
            await deleteCategory(spaceId.value, item.id);
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
        uni.showToast({ title: `已删除 ${targets.length} 个`, icon: 'success' });
      }
    },
  });
}

// 用 onShow 而不是 onLoad：从别的页面返回时也会重新拉一次，
// 保证（比如在菜品管理里换了分类之后）回到这页看到的数量是最新的
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
/* 状态取代标题：与右边按钮同高，读起来是一条工具条 */
.page-status { color: var(--c-text-2); font-size: 23rpx; }
.page-desc { color: var(--c-text-2); font-size: 22rpx; line-height: 1.55; }
/* 右上角动作组：新增（实心主色）+ 批量删除（描边），层次与菜品管理页一致 */
.head-actions { flex: 0 0 auto; display: flex; align-items: center; gap: var(--s-2); }
.head-btn.primary {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
}
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
  min-height: 120rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.row:last-child { border-bottom: none; }

/* 空态：虚线卡片，和购物车/收藏页的空态长得一样，用户一眼认得出"这里还没东西" */
.empty-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-5) var(--s-4);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-lg);
  background: var(--c-surface);
}
.empty-title { color: var(--c-text); font-size: 28rpx; font-weight: 500; }
.empty-copy { color: var(--c-text-2); font-size: 24rpx; line-height: 1.65; }
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

.row-actions { flex: 0 0 auto; display: flex; align-items: center; gap: var(--s-1); }
/* 行内动作只剩下「改名」——删除收进右上角的批量入口了。
   88rpx 的点击区保留：比小按钮好点，也不差这点宽 */
.action {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 96rpx;
  height: var(--touch-min);
  padding: 0 var(--s-2);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-sm);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 25rpx;
}

/* 勾中的行加一层浅底 */
.row.picked { background: var(--c-primary-bg); }
/* 还有菜的分类：压暗 + 不可勾（点了会说明原因，见 explainLocked） */
.row.locked .row-name { color: var(--c-text-2); }
.row.locked .check { border-style: dashed; background: var(--c-muted); }

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
.check.on { border-color: var(--c-primary); background: var(--c-primary); border-style: solid; }
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

/* 批量操作栏：固定在底部（本页不是 tabBar 页，bottom:0 就是屏幕底） */
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
.select-delete.disabled { background: var(--c-muted); color: var(--c-text-3); }

/* 底部有操作栏时给页面留出空间，别让最后一行被盖住 */
.manage-page.with-bar { padding-bottom: calc(220rpx + env(safe-area-inset-bottom)); }

.page-note {
  display: block;
  margin-top: var(--s-3);
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.7;
  text-align: center;
}
</style>
