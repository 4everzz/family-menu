<template>
  <view class="manage-page">
    <view class="page-head">
      <text class="page-title">菜单分类</text>
      <text class="page-desc">
        分类是你们家自己的一套，可以随意增加、改名、删除。
        改了名字，归在这一类下的菜会自动跟着显示新名字，不用一个个去改。
      </text>
    </view>

    <view v-if="loading" class="tip">正在读取…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <view class="retry-btn" hover-class="tap" @click="load">重试</view>
    </view>

    <template v-else>
      <view class="list">
        <view v-for="item in categories" :key="item.id" class="row">
          <view class="row-main">
            <text class="row-name">{{ item.name }}</text>
            <text class="row-meta">{{ item.recipeCount }} 道菜</text>
          </view>
          <view class="row-actions">
            <view class="action" hover-class="tap" @click="rename(item)">改名</view>
            <view class="action danger" hover-class="tap" @click="remove(item)">删除</view>
          </view>
        </view>
      </view>

      <view class="add-btn" hover-class="tap" @click="add">+ 新增分类</view>

      <text class="page-note">分类下还有菜的时候不能删除——先把那些菜改到别的分类，再来删。</text>
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

import { ref } from 'vue';
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
 * 删除分类。
 *
 * 两条分支要分开处理：
 *   还有菜 → 直接说清楚"有几道菜、该怎么办"，不给删除按钮（给了也删不掉，是耍人）；
 *   没有菜 → 才走正常的二次确认。
 * 这个数量判断用的是后端返回的 recipeCount（全量口径），不会因为搜索过而算少。
 */
function remove(item: Category): void {
  if (pending.value) return;

  if (item.recipeCount > 0) {
    uni.showModal({
      title: '这个分类还不能删',
      content: `「${item.name}」下还有 ${item.recipeCount} 道菜。请先把这些菜改到别的分类，再来删除这个分类。`,
      showCancel: false,
      confirmText: '知道了',
    });
    return;
  }

  uni.showModal({
    title: '删除分类',
    content: `确定要删除「${item.name}」吗？这个分类下目前没有菜谱。`,
    confirmText: '删除',
    confirmColor: DANGER,
    success: async (result) => {
      if (!result.confirm) return;
      pending.value = true;
      uni.showLoading({ title: '删除中' });
      try {
        await deleteCategory(spaceId.value, item.id);
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

.page-head { display: flex; flex-direction: column; gap: var(--s-1); margin: 0 var(--s-1) var(--s-4); }
.page-title { color: var(--c-text); font-size: 40rpx; font-weight: 500; }
.page-desc { color: var(--c-text-2); font-size: 24rpx; line-height: 1.7; }

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
/* 每个操作都做成至少 88rpx 宽的点击区：小屏上"改名/删除"挨太近很容易点错 */
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
.action.danger { border-color: var(--c-danger-border); color: var(--c-danger); }

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
.page-note {
  display: block;
  margin-top: var(--s-3);
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.7;
  text-align: center;
}
</style>
