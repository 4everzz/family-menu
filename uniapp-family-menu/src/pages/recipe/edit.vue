<template>
  <view class="edit-page">
    <view v-if="loading" class="tip">正在读取…</view>

    <template v-else>
      <view class="form-card">
        <view class="field-group">
          <text class="field-label">菜名</text>
          <input
            v-model="form.name"
            class="field-input"
            :class="{ focused: focusedField === 'name' }"
            placeholder="例如：番茄炒蛋"
            placeholder-class="field-placeholder"
            maxlength="64"
            @focus="focusedField = 'name'"
            @blur="focusedField = ''"
          />
        </view>

        <view class="field-group">
          <text class="field-label">归到哪一类</text>
          <!-- 分类清单完全来自后端，前端不硬编码。
               用户可以自己增删改分类，所以这里必须是动态的。 -->
          <view v-if="categories.length" class="category-picker">
            <view
              v-for="item in categories"
              :key="item.id"
              class="category-chip"
              :class="{ active: form.categoryId === item.id }"
              @click="form.categoryId = item.id"
            >
              {{ item.name }}
            </view>
          </view>
          <view v-else class="category-empty">
            这个家还没有分类。先去「我的 → 菜单管理 → 分类管理」建一个，才能添加菜谱。
          </view>
        </view>

        <view class="field-group">
          <view class="field-head">
            <text class="field-label">做法 / 说明</text>
            <text class="field-count">{{ form.description.length }} / 2000</text>
          </view>
          <textarea
            v-model="form.description"
            class="field-textarea"
            :class="{ focused: focusedField === 'description' }"
            maxlength="2000"
            placeholder="想怎么写都行，比如「鸡蛋先炒散盛出，番茄去皮再下锅」"
            placeholder-class="field-placeholder"
            @focus="focusedField = 'description'"
            @blur="focusedField = ''"
          />
        </view>
      </view>

      <view class="save-btn" :class="{ disabled: !canSave }" @click="submit">
        {{ pending ? '正在保存…' : isEdit ? '保存修改' : '加进菜谱' }}
      </view>

      <!-- 删除放在这个页面里，列表页的卡片上不放开删的入口，少一次误触 -->
      <view v-if="isEdit" class="delete-btn" @click="confirmDelete">删除这道菜</view>

      <text v-if="metaLine" class="page-note">{{ metaLine }}</text>
    </template>
  </view>
</template>

<script setup lang="ts">
/**
 * 菜谱编辑页：新增和编辑共用一个页面。
 *
 * 为什么合一？
 *   两种模式的字段完全一样、校验完全一样，唯一的差别是"加载已有数据"和
 *   "调新增还是调修改"。拆成两个页面会带来两份几乎相同的表单代码，
 *   以后加一个字段要改两处，早晚会漏。
 *
 * 用法（入口都在「我的 → 菜单管理 → 菜品管理」）：
 *   /pages/recipe/edit        → 新增
 *   /pages/recipe/edit?id=12  → 编辑第 12 道菜
 *
 * 注意本页不再从菜单页进入——菜单页已经改成纯浏览，
 * 点菜谱卡片进的是只读详情页 pages/recipe/detail.vue。
 */

import { computed, reactive, ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import { ensureLogin } from '../../services/auth-api';
import type { Category } from '../../services/category';
import { fetchCategories } from '../../services/category';
import { createRecipe, deleteRecipe, fetchRecipe, updateRecipe } from '../../services/recipe';
import { getCurrentSpaceId } from '../../utils/space-context';
import { showError } from '../../utils/format';

const spaceId = ref('');
const recipeId = ref('');
const categories = ref<Category[]>([]);
const loading = ref(true);
/** 请求进行中标记：防止连点导致重复提交（新增接口不是幂等的，连点会加出两条） */
const pending = ref(false);
/** 当前聚焦的字段名，用来把输入框描边点亮。小程序没有 CSS :focus，只能用 JS 标记 */
const focusedField = ref('');
/** 编辑模式下显示「由谁添加」，给用户一点上下文 */
const metaLine = ref('');

/** 表单内容。用 reactive 而不是四个 ref，改起来更整齐 */
const form = reactive({ name: '', categoryId: '', description: '', imageUrl: '' });

const isEdit = computed(() => !!recipeId.value);
/** 菜名必填、分类必选（后端也校验，这里只是避免白跑一次请求） */
const canSave = computed(() => !pending.value && !!form.name.trim() && !!form.categoryId);

/**
 * 新增时默认选中哪个分类。
 *
 * 优先用后端标记的 is_default（目前是「热菜」），拿不到就退化成第一个。
 * 为什么不在这里写死「热菜」这个字符串：用户可以给分类改名，
 * 硬编码的话改完名这个默认值就悄悄失效了——不报错，只是每次加菜都要手动改一下分类。
 */
function pickDefaultCategoryId(): string {
  const preferred = categories.value.find((item) => item.isDefault);
  return preferred?.id || categories.value[0]?.id || '';
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    await ensureLogin();
    spaceId.value = getCurrentSpaceId();

    // 正常流程不会走到这里（入口页已经拦了），防御一下：没有家庭组就没法存菜谱
    if (!spaceId.value) {
      showError('还没有选择家庭组');
      setTimeout(() => uni.navigateBack(), 900);
      return;
    }

    categories.value = await fetchCategories(spaceId.value);

    if (isEdit.value) {
      const recipe = await fetchRecipe(spaceId.value, recipeId.value);
      form.name = recipe.name;
      form.categoryId = recipe.categoryId;
      form.description = recipe.description;
      form.imageUrl = recipe.imageUrl;
      metaLine.value = recipe.createdByName ? `由 ${recipe.createdByName} 添加` : '';
      uni.setNavigationBarTitle({ title: '编辑菜谱' });
    } else {
      form.categoryId = pickDefaultCategoryId();
      uni.setNavigationBarTitle({ title: '新增菜谱' });
    }
  } catch (error) {
    showError(error instanceof Error ? error.message : '读取失败，请稍后重试');
  } finally {
    loading.value = false;
  }
}

async function submit(): Promise<void> {
  if (!canSave.value) return;
  pending.value = true;
  try {
    const payload = {
      name: form.name.trim(),
      categoryId: form.categoryId,
      description: form.description,
      imageUrl: form.imageUrl,
    };

    if (isEdit.value) await updateRecipe(spaceId.value, recipeId.value, payload);
    else await createRecipe(spaceId.value, payload);

    uni.showToast({ title: isEdit.value ? '已保存' : '已添加', icon: 'success' });
    // 等一下再返回，让提示能被看见；列表页的 onShow 会自动刷新出最新数据
    setTimeout(() => uni.navigateBack(), 600);
  } catch (error) {
    showError(error instanceof Error ? error.message : '保存失败，请重试');
  } finally {
    pending.value = false;
  }
}

/**
 * 删除菜谱。
 *
 * 必须二次确认：本版本「谁都能删」是由权限模型决定的（见后端 RecipeService 的说明），
 * 代价就用这道确认来兜——菜谱是全家一起攒的，误删一条别人加的菜很伤感情。
 */
function confirmDelete(): void {
  if (pending.value) return;
  uni.showModal({
    title: '删除这道菜',
    content: `确定要把「${form.name}」从家庭菜谱里删掉吗？删除后无法恢复。`,
    confirmText: '删除',
    confirmColor: '#dc2626',
    success: async (result) => {
      if (!result.confirm) return;
      pending.value = true;
      try {
        await deleteRecipe(spaceId.value, recipeId.value);
        uni.showToast({ title: '已删除', icon: 'success' });
        setTimeout(() => uni.navigateBack(), 600);
      } catch (error) {
        showError(error instanceof Error ? error.message : '删除失败，请重试');
      } finally {
        pending.value = false;
      }
    },
  });
}

onLoad((options) => {
  recipeId.value = String(options?.id ?? '');
  void load();
});
</script>

<style scoped>
.edit-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}
.tip { display: block; margin-top: 60rpx; color: var(--c-text-3); font-size: 24rpx; text-align: center; }

/* 整张表单放一张卡片里：输入框之间靠间距分组，视觉上比"一堆散落的框"整齐得多 */
.form-card {
  padding: var(--s-4) var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
}

.field-group { display: flex; flex-direction: column; gap: var(--s-2); margin-bottom: var(--s-4); }
.field-group:last-child { margin-bottom: 0; }
.field-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-2); }
.field-label { color: var(--c-text-2); font-size: 24rpx; }
.field-count { color: var(--c-text-3); font-size: 21rpx; }

.field-input {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 30rpx;
  font-weight: 500;
  box-sizing: border-box;
}
.field-textarea {
  width: 100%;
  min-height: 320rpx;
  padding: var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-muted);
  color: var(--c-text);
  font-size: 27rpx;
  line-height: 1.65;
  box-sizing: border-box;
}
/* 聚焦态：小程序没有 CSS :focus，靠 JS 加类名。
   不加这个的话，用户点进输入框没有任何反馈，会不确定"到底选中了没"。 */
.field-input.focused, .field-textarea.focused {
  border-color: var(--c-primary);
  background: var(--c-surface);
}
:deep(.field-placeholder) { color: var(--c-text-3); font-weight: 400; }

.category-picker { display: flex; flex-wrap: wrap; gap: var(--s-2); }
/* 药丸形标签：够大（88rpx 高）能稳定点中，又比一排大按钮省地方 */
.category-chip {
  display: flex;
  align-items: center;
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-pill);
  background: var(--c-surface);
  color: var(--c-text-2);
  font-size: 26rpx;
}
.category-chip.active {
  border-color: var(--c-primary);
  background: var(--c-primary);
  color: #fff;
  font-weight: 500;
}
.category-empty {
  padding: var(--s-3);
  border: 2rpx dashed var(--c-border-strong);
  border-radius: var(--r-md);
  color: var(--c-text-2);
  font-size: 24rpx;
  line-height: 1.6;
}

.save-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 96rpx;
  margin-top: var(--s-4);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  font-weight: 500;
}
.save-btn.disabled { background: #ddc4b8; }
.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 96rpx;
  margin-top: var(--s-3);
  border: 2rpx solid #f7c1c1;
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-danger);
  font-size: 28rpx;
  font-weight: 500;
}
.page-note { display: block; margin-top: var(--s-4); color: var(--c-text-3); font-size: 22rpx; text-align: center; }
</style>
