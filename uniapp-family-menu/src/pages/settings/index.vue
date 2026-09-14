<template>
  <view class="settings-page">
    <!-- 账号：先让用户看清"现在是谁在登录"，再决定要不要换 -->
    <view class="group">
      <text class="group-title">账号</text>
      <view class="entry-group">
        <view class="identity">
          <image v-if="avatarUrl" class="avatar-img" :src="avatarUrl" mode="aspectFill" />
          <view v-else class="avatar-fallback">{{ avatarText }}</view>
          <view class="identity-main">
            <text class="identity-name">{{ nickname || '未登录' }}</text>
            <text class="identity-desc">微信身份，登录状态由本机保存</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 家庭：切换、创建、加入统一收在这里，菜单页不再有入口 -->
    <view class="group">
      <text class="group-title">家庭</text>
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="goSpace">
          <view class="entry-main">
            <text class="entry-name">切换家庭</text>
            <text class="entry-desc">当前：{{ spaceName || '未加入家庭组' }}</text>
          </view>
          <text class="entry-arrow">›</text>
        </view>
      </view>
    </view>

    <!-- 账号操作：破坏性操作用危险色，和上面的浏览类条目区分开 -->
    <view class="group">
      <view class="entry-group">
        <view class="entry-item" hover-class="tap" @click="switchAccount">
          <view class="entry-main">
            <text class="entry-name danger-text">切换账号</text>
            <text class="entry-desc">清除本机登录状态后重新登录</text>
          </view>
        </view>
      </view>
    </view>

    <text class="page-note">更多设置项会在后续模块加入</text>
  </view>
</template>

<script setup lang="ts">
/**
 * 设置页。
 *
 * 为什么要有这一页？
 *   「切换家庭」原来分散在菜单页和「我的」页的卡片上，点一下就能换家。
 *   但换家会连带影响菜谱、冰箱这些家庭共享数据——它属于"配置类"动作，
 *   不该和"看菜单"混在同一个手势里。所以统一收进设置页，
 *   菜单页只负责显示"现在看的是哪个家"，不再提供切换。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { fetchCurrentUser } from '../../services/user';
import { ensureLogin } from '../../services/auth-api';
import { clearToken, hasValidToken } from '../../utils/token';
import { PRIMARY } from '../../utils/theme';
import { getCurrentSpaceName, resolveCurrentSpace, setCurrentSpace } from '../../utils/space-context';

const nickname = ref('');
const avatarUrl = ref('');
const spaceName = ref('');
/** 防止连点导致重复弹窗/重复请求 */
const pending = ref(false);

/** 没有头像时用昵称首字当占位，比一个空白圆好看，也比放通用图轻 */
const avatarText = computed(() => (nickname.value || '微').slice(0, 1));

async function refresh(): Promise<void> {
  // 先用本地缓存把界面填上，避免进页面先空一下
  spaceName.value = getCurrentSpaceName();

  if (!hasValidToken()) return;

  try {
    const user = await fetchCurrentUser();
    nickname.value = user.nickname;
    avatarUrl.value = user.avatarUrl;
  } catch (error) {
    // 读取失败（例如后端没启动）不打断页面，保留默认文案
  }

  try {
    await resolveCurrentSpace();
    spaceName.value = getCurrentSpaceName();
  } catch (error) {
    // 同上：拿不到列表就沿用缓存里的名字
  }
}

/** 切换/创建/加入家庭组都在家庭组页面里 */
function goSpace(): void {
  uni.navigateTo({ url: '/pages/space/index' });
}

/**
 * 切换账号。
 *
 * ⚠️ 这里必须说实话：**微信小程序的身份由微信账号决定**，没有"在小程序内换个人"这回事。
 * 所以这个动作的真实语义是——清掉本机保存的登录状态，然后重新登录一次。
 * 如果你的微信账号没变，登录后还是同一个人；要换成别人，得先在微信里切换账号。
 * 确认文案里把这一点讲清楚，免得用户以为点一下就能变成另一个人。
 */
function switchAccount(): void {
  if (pending.value) return;
  uni.showModal({
    title: '切换账号',
    content:
      '小程序里的身份由你的微信账号决定。这里会清除本机保存的登录状态（含当前家庭组）并重新登录；如果微信账号没变，登录后仍是同一个人。要换成别人，请先在微信里切换账号。',
    confirmText: '继续',
    confirmColor: PRIMARY,
    success: async (res) => {
      if (!res.confirm) return;
      pending.value = true;
      uni.showLoading({ title: '正在重新登录' });
      try {
        clearToken();
        // 家庭缓存必须一起清：否则换了账号还带着上一个人的"当前家庭"，会请求到别人的数据
        setCurrentSpace(null);
        spaceName.value = '';
        nickname.value = '';
        avatarUrl.value = '';

        await ensureLogin();
        await refresh();
        uni.showToast({ title: '已重新登录', icon: 'none' });
      } catch (error) {
        uni.showToast({
          title: error instanceof Error ? error.message : '重新登录失败，请稍后重试',
          icon: 'none',
        });
      } finally {
        uni.hideLoading();
        pending.value = false;
      }
    },
  });
}

onShow(refresh);
</script>

<style scoped>
.settings-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.group { margin-bottom: var(--s-4); }
.group-title {
  display: block;
  margin: 0 var(--s-1) var(--s-2);
  color: var(--c-text-2);
  font-size: 23rpx;
}

.entry-group {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

/* 身份卡片：比普通条目高一点，让"我是谁"这个信息更醒目 */
.identity {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  min-height: 136rpx;
  padding: var(--s-2) var(--s-3);
}
.avatar-img,
.avatar-fallback {
  flex: 0 0 auto;
  width: 88rpx;
  height: 88rpx;
  border-radius: 50%;
}
.avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-primary-bg);
  color: var(--c-primary);
  font-size: 36rpx;
  font-weight: 500;
}
.identity-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.identity-name {
  overflow: hidden;
  color: var(--c-text);
  font-size: 30rpx;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.identity-desc { color: var(--c-text-2); font-size: 23rpx; }

.entry-item {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 120rpx;
  padding: var(--s-2) var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.entry-item:last-child { border-bottom: none; }
.entry-main { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.entry-name { color: var(--c-text); font-size: 29rpx; font-weight: 500; }
.entry-desc {
  overflow: hidden;
  color: var(--c-text-2);
  font-size: 23rpx;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-arrow { flex: 0 0 auto; color: var(--c-text-3); font-size: 40rpx; line-height: 1; }

/* 破坏性操作：文案用危险色，提示这条和上面的浏览类条目不是一回事 */
.danger-text { color: var(--c-danger); }

.page-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  text-align: center;
}
</style>
