<template>
  <view class="space-page">
    <!-- 当前家庭组：切换后冰箱等家庭共享数据都会跟着变 -->
    <view class="current-card">
      <text class="current-label">当前家庭</text>
      <text class="current-name">{{ currentName || '未加入家庭组' }}</text>
    </view>

    <view v-if="loading" class="tip">正在读取家庭组…</view>

    <view v-else-if="errorMessage" class="error-card">
      <text class="error-text">{{ errorMessage }}</text>
      <text class="error-hint">家庭组功能需要后端处于启动状态；在微信开发者工具里还需勾选「不校验合法域名」。</text>
      <view class="retry-btn" @click="load">重试</view>
    </view>

    <template v-else>
      <text v-if="spaces.length" class="group-title">我的家庭组 · {{ spaces.length }}</text>

      <view
        v-for="item in spaces"
        :key="item.id"
        class="space-item"
        :class="{ selected: item.id === currentId }"
        @click="switchTo(item)"
      >
        <view class="space-row">
          <view class="space-main">
            <text class="space-name">{{ item.name }}</text>
            <text class="space-meta">{{ roleText(item) }}</text>
          </view>
          <text v-if="item.id === currentId" class="badge">当前</text>
        </view>

        <!-- 邀请码只有管理员看得到，这是后端控制的，普通成员这里不会有这一行 -->
        <view v-if="item.inviteCode" class="invite-row" @click.stop="copyCode(item.inviteCode)">
          <text class="invite-label">邀请码</text>
          <text class="invite-code">{{ item.inviteCode }}</text>
          <text class="invite-action">复制</text>
        </view>
      </view>

      <view v-if="!spaces.length" class="empty-card">
        <text class="empty-title">还没有家庭组</text>
        <text class="empty-copy">创建一个，把家人拉进来；也可以让家人把邀请码发给你，用下面的入口加入。</text>
      </view>

      <view class="action-card">
        <view class="action-head" @click="creating = !creating">
          <text class="action-name">创建家庭组</text>
          <text class="action-sign">{{ creating ? '收起' : '展开' }}</text>
        </view>
        <view v-if="creating" class="action-body">
          <input v-model="createName" class="field" placeholder="给家庭组起个名字，例如「张家」" maxlength="32" />
          <view class="submit-btn" :class="{ disabled: createDisabled }" @click="submitCreate">创建</view>
        </view>
      </view>

      <view class="action-card">
        <view class="action-head" @click="joining = !joining">
          <text class="action-name">用邀请码加入</text>
          <text class="action-sign">{{ joining ? '收起' : '展开' }}</text>
        </view>
        <view v-if="joining" class="action-body">
          <input v-model="joinCode" class="field" placeholder="输入家人分享的 8 位邀请码" maxlength="16" />
          <view class="submit-btn" :class="{ disabled: joinDisabled }" @click="submitJoin">加入</view>
        </view>
      </view>

      <text class="page-note">创建家庭组的人即管理员，可以看到邀请码；组内所有成员都能点菜、记录冰箱。</text>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import {
  getCurrentSpaceId,
  getCurrentSpaceName,
  resolveCurrentSpace,
  setCurrentSpace,
} from '../../utils/space-context';
import type { SpaceInfo } from '../../utils/space-context';
import { createSpace, joinSpace } from '../../services/space';
import { ensureLogin } from '../../services/auth-api';

const spaces = ref<SpaceInfo[]>([]);
const currentId = ref(getCurrentSpaceId());
const currentName = ref(getCurrentSpaceName());
const loading = ref(true);
const errorMessage = ref('');

const creating = ref(false);
const createName = ref('');
const joining = ref(false);
const joinCode = ref('');
/** 请求进行中标记：防止连点导致重复创建 */
const pending = ref(false);

const createDisabled = computed(() => pending.value || !createName.value.trim());
const joinDisabled = computed(() => pending.value || !joinCode.value.trim());

/** 列表里那行小字：我的角色和成员数 */
function roleText(item: SpaceInfo): string {
  const role = item.myRole === 'admin' ? '管理员' : '成员';
  return `${role} · ${item.memberCount ?? 1} 人`;
}

/** 把页面上的"当前家庭"刷新成缓存里的值 */
function refreshCurrent(): void {
  currentId.value = getCurrentSpaceId();
  currentName.value = getCurrentSpaceName();
}

/** 加载列表（每次进入页面都刷新一次，保证看到的是最新的） */
async function load(): Promise<void> {
  loading.value = true;
  errorMessage.value = '';
  try {
    // 先确保登录态：首次进入或令牌过期时会自动登录，用户无感
    await ensureLogin();
    spaces.value = await resolveCurrentSpace();
    refreshCurrent();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '读取家庭组失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}

/**
 * 切换当前家庭组
 * @param silent 由创建/加入流程调用时传 true，避免和后面的提示重复弹两次
 */
function switchTo(item: SpaceInfo, silent = false): void {
  if (item.id === currentId.value) return;
  setCurrentSpace(item);
  refreshCurrent();
  if (!silent) uni.showToast({ title: `已切换到 ${item.name}`, icon: 'none' });
}

/** 复制邀请码：家人之间大多是复制粘贴分享 */
function copyCode(code?: string | null): void {
  if (!code) return;
  uni.setClipboardData({
    data: code,
    success: () => uni.showToast({ title: '邀请码已复制', icon: 'none' }),
    fail: () => uni.showToast({ title: '复制失败，请手动记录', icon: 'none' }),
  });
}

async function submitCreate(): Promise<void> {
  const name = createName.value.trim();
  if (!name || pending.value) return;

  pending.value = true;
  try {
    const space = await createSpace(name);
    createName.value = '';
    creating.value = false;
    await load();
    // 刚创建的家庭组直接设为当前，用户马上就能开始用
    switchTo(space, true);
    uni.showToast({ title: `已创建「${space.name}」`, icon: 'none' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '创建失败，请重试', icon: 'none' });
  } finally {
    pending.value = false;
  }
}

async function submitJoin(): Promise<void> {
  const code = joinCode.value.trim();
  if (!code || pending.value) return;

  pending.value = true;
  try {
    const space = await joinSpace(code);
    joinCode.value = '';
    joining.value = false;
    await load();
    switchTo(space, true);
    uni.showToast({ title: `已加入「${space.name}」`, icon: 'none' });
  } catch (error) {
    uni.showToast({ title: error instanceof Error ? error.message : '加入失败，请重试', icon: 'none' });
  } finally {
    pending.value = false;
  }
}

onShow(load);
</script>

<style scoped>
.space-page { min-height: 100vh; padding: 28rpx 24rpx calc(48rpx + env(safe-area-inset-bottom)); box-sizing: border-box; }
.current-card { display: flex; flex-direction: column; gap: 10rpx; padding: 30rpx 26rpx; border: 2rpx solid #fecaca; border-radius: 22rpx; background: #fff; box-shadow: 0 8rpx 20rpx rgba(69, 10, 10, .05); }
.current-label { color: #78716c; font-size: 23rpx; }
.current-name { color: #450a0a; font-size: 34rpx; font-weight: 800; }
.tip { display: block; margin-top: 40rpx; color: #a8a29e; font-size: 24rpx; text-align: center; }
.error-card { display: flex; flex-direction: column; gap: 14rpx; margin-top: 28rpx; padding: 30rpx 26rpx; border: 2rpx solid #fecaca; border-radius: 20rpx; background: #fff; }
.error-text { color: #b91c1c; font-size: 27rpx; font-weight: 700; }
.error-hint { color: #78716c; font-size: 23rpx; line-height: 1.6; }
.retry-btn { align-self: flex-start; padding: 14rpx 32rpx; border-radius: 999rpx; background: #dc2626; color: #fff; font-size: 25rpx; font-weight: 700; }
.group-title { display: block; margin: 34rpx 0 16rpx; color: #78716c; font-size: 23rpx; }
.space-item { display: flex; flex-direction: column; gap: 18rpx; margin-bottom: 18rpx; padding: 26rpx; border: 2rpx solid #fee2e2; border-radius: 20rpx; background: #fff; box-shadow: 0 8rpx 18rpx rgba(69, 10, 10, .04); }
.space-item.selected { border-color: #dc2626; background: #fff7ed; }
.space-row { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; }
.space-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 8rpx; }
.space-name { color: #450a0a; font-size: 30rpx; font-weight: 700; }
.space-meta { color: #78716c; font-size: 23rpx; }
.badge { flex: 0 0 auto; padding: 8rpx 18rpx; border-radius: 999rpx; background: #dc2626; color: #fff; font-size: 22rpx; font-weight: 700; }
.invite-row { display: flex; align-items: center; gap: 14rpx; padding: 16rpx 20rpx; border-radius: 14rpx; background: #fff7ed; }
.invite-label { color: #7c2d12; font-size: 23rpx; }
.invite-code { flex: 1; color: #450a0a; font-size: 27rpx; font-weight: 800; letter-spacing: 2rpx; }
.invite-action { color: #b91c1c; font-size: 23rpx; font-weight: 700; }
.empty-card { display: flex; flex-direction: column; gap: 12rpx; margin-top: 20rpx; padding: 40rpx 30rpx; border: 2rpx dashed #fecaca; border-radius: 20rpx; background: #fff; }
.empty-title { color: #450a0a; font-size: 29rpx; font-weight: 700; }
.empty-copy { color: #78716c; font-size: 24rpx; line-height: 1.6; }
.action-card { margin-top: 18rpx; border: 2rpx solid #fee2e2; border-radius: 20rpx; background: #fff; overflow: hidden; }
.action-head { display: flex; align-items: center; justify-content: space-between; padding: 26rpx; }
.action-name { color: #450a0a; font-size: 28rpx; font-weight: 700; }
.action-sign { color: #b91c1c; font-size: 23rpx; font-weight: 700; }
.action-body { display: flex; flex-direction: column; gap: 18rpx; padding: 0 26rpx 26rpx; }
.field { height: 84rpx; padding: 0 22rpx; border: 2rpx solid #fee2e2; border-radius: 16rpx; background: #fff7ed; color: #431407; font-size: 27rpx; }
.submit-btn { display: flex; align-items: center; justify-content: center; height: 84rpx; border-radius: 16rpx; background: #dc2626; color: #fff; font-size: 28rpx; font-weight: 700; }
.submit-btn.disabled { background: #f5c4b3; }
.page-note { display: block; margin-top: 34rpx; color: #a8a29e; font-size: 22rpx; line-height: 1.6; text-align: center; }
</style>
