<template>
  <view class="cred-page">
    <!-- 顶部说明：同一个页面要服务两种完全不同的处境，
         所以先把"你现在是什么状态、这一页能干什么"讲清楚 -->
    <view class="intro">
      <text class="intro-title">{{ isFirstTime ? '还没有账号密码' : '账号密码' }}</text>
      <text class="intro-desc">{{ introDesc }}</text>
    </view>

    <view class="group">
      <text class="group-title">登录用户名</text>
      <view class="entry-group">
        <view class="field-row">
          <input
            v-model="usernameInput"
            class="field-input"
            :maxlength="USERNAME_MAX_LENGTH"
            placeholder="字母、数字或下划线"
            placeholder-class="field-placeholder"
            :disabled="saving"
          />
        </view>
      </view>
      <text class="field-hint">
        登录用它；显示给家人的「昵称」是另一回事，在「编辑资料」里改
      </text>
    </view>

    <view class="group">
      <text class="group-title">{{ isFirstTime ? '设置密码' : '新密码' }}</text>
      <view class="entry-group">
        <view class="field-row">
          <input
            v-model="passwordInput"
            class="field-input"
            password
            :maxlength="PASSWORD_MAX_LENGTH"
            :placeholder="isFirstTime ? `至少 ${PASSWORD_MIN_LENGTH} 位` : '留空表示这次不改密码'"
            placeholder-class="field-placeholder"
            :disabled="saving"
          />
        </view>
        <view class="field-row">
          <input
            v-model="confirmInput"
            class="field-input"
            password
            :maxlength="PASSWORD_MAX_LENGTH"
            placeholder="再输一遍新密码"
            placeholder-class="field-placeholder"
            :disabled="saving || (!isFirstTime && !wantsPasswordChange)"
          />
        </view>
      </view>
    </view>

    <!-- 当前密码：只在"这个账号已经有密码"时出现，而且必填。
         它是"手机被别人拿到"的防线——没有它，捡到一台已登录的手机就能改密码夺号。 -->
    <view v-if="!isFirstTime" class="group">
      <text class="group-title">当前密码</text>
      <view class="entry-group">
        <view class="field-row">
          <input
            v-model="currentInput"
            class="field-input"
            password
            :maxlength="PASSWORD_MAX_LENGTH"
            placeholder="改密码或用户名要先确认是你本人"
            placeholder-class="field-placeholder"
            :disabled="saving"
          />
        </view>
      </view>
    </view>

    <button
      class="save-btn"
      hover-class="tap"
      :class="{ 'save-btn--disabled': !canSave }"
      :disabled="!canSave"
      @click="onSave"
    >
      {{ saving ? '保存中…' : isFirstTime ? '设置账号密码' : '保存修改' }}
    </button>

    <text v-if="!isFirstTime" class="page-note">
      改完密码后，本机已登录的状态不受影响（令牌到期前仍然有效）。
    </text>
  </view>
</template>

<script setup lang="ts">
/**
 * 设置 / 修改账号密码页。
 *
 * ⭐ 为什么需要这一页？
 *   在此之前**注册之后就再也改不了密码** —— 用户被撞库了都没法换密码。
 *   另外改造前用微信登录进来的老账号（库里 username / password_hash 都是空）
 *   一直没地方补一套账号密码，于是它们永远登不了 App。
 *   这一页把两件事一起解决，靠"有没有用户名"自动切换形态。
 *
 * 页面有两种形态，**由数据决定、不用用户选**：
 *   · 首次设置 —— 还没用户名。要求：用户名 + 新密码 + 确认（不用当前密码）
 *   · 修改     —— 已有用户名。要求：当前密码必填；用户名/新密码至少改一样
 *
 * ⚠️ 前端这几条校验只是"别白打一次请求"，**规则以后端为准**。
 *    接口是公开的，绕过界面直接调一样能提交，所以真正的闸门都在服务端。
 *    （服务端那边：已有密码必须验当前密码、用户名查重、密码不能等于用户名。）
 *
 * ⚠️ 改密码**不会**让已经发出去的令牌失效（无状态 JWT、没有版本号）。
 *    这是已知限制，页面底部如实告诉用户，别让人以为别处会被踢下线。
 */

import { computed, ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { setCredentials, type CredentialsInput } from '../../services/auth-api';
import { fetchCurrentUser, type CurrentUser } from '../../services/user';
import { showError } from '../../utils/format';
import { hasValidToken } from '../../utils/token';

// 长度限制前后端各写一份是无法避免的（后端是权威）。
// 这里显式写出来而不是散在模板里，是为了"改限制时能一眼看到有两处"。
const USERNAME_MAX_LENGTH = 20;
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 64;

const user = ref<CurrentUser | null>(null);
const usernameInput = ref('');
const passwordInput = ref('');
const confirmInput = ref('');
const currentInput = ref('');
const saving = ref(false);

/** 首次设置 = 库里还没有用户名（微信登录进来的老账号就是这个形态） */
const isFirstTime = computed(() => !user.value?.username);

const introDesc = computed(() => {
  if (isFirstTime.value) {
    return '你这个账号是用微信登录进来的，还没有自己的用户名和密码。设一套之后，就能用它在 App 上直接登录了。';
  }
  return `当前用 @${user.value?.username} 登录。改完之后要用新的一套登录。`;
});

/** 用户名归一化：和后端一致（去空格 + 转小写），否则"改了没改"会判断错 */
const trimmedUsername = computed(() => usernameInput.value.trim().toLowerCase());

/** 用户名这次有没有真的改动 */
const usernameChanged = computed(() => trimmedUsername.value !== (user.value?.username ?? ''));

/** 用户是不是想改密码（新密码框有内容） */
const wantsPasswordChange = computed(() => passwordInput.value.length > 0);

const canSave = computed(() => {
  if (saving.value || !user.value) return false;

  if (isFirstTime.value) {
    // 首次设置：三样都得填 —— 只给用户名没密码登不了，只给密码没有登录名
    return (
      trimmedUsername.value.length > 0 &&
      passwordInput.value.length >= PASSWORD_MIN_LENGTH &&
      confirmInput.value.length > 0
    );
  }

  // 修改：至少改了用户名或密码其中一样，否则是"什么都没做"
  if (!usernameChanged.value && !wantsPasswordChange.value) return false;
  // 现有账号改任何东西都要验当前密码
  if (!currentInput.value) return false;
  // 想改密码就得把确认也填上
  if (wantsPasswordChange.value && confirmInput.value.length === 0) return false;
  return true;
});

/** 拉当前用户，并把用户名预填进输入框（修改形态下要能看见现在叫什么） */
async function load(): Promise<void> {
  if (!hasValidToken()) return;
  try {
    const current = await fetchCurrentUser();
    user.value = current;
    usernameInput.value = current.username;
  } catch {
    // 拉不到就保持空态：这一页本来就要靠数据才能用，弹错误只会干扰
  }
}

async function onSave(): Promise<void> {
  if (!canSave.value) return;

  // 前端先挡住最明显的两条，少打一次注定失败的请求
  if (wantsPasswordChange.value) {
    if (passwordInput.value.length < PASSWORD_MIN_LENGTH) {
      uni.showToast({ title: `密码至少 ${PASSWORD_MIN_LENGTH} 位`, icon: 'none' });
      return;
    }
    if (passwordInput.value !== confirmInput.value) {
      uni.showToast({ title: '两次输入的密码不一致', icon: 'none' });
      return;
    }
  }

  // 只把"真的要改"的字段放进请求体（后端按"传了哪些字段"判断要改什么）
  const payload: CredentialsInput = {};
  if (isFirstTime.value || usernameChanged.value) {
    payload.username = trimmedUsername.value;
  }
  if (wantsPasswordChange.value) {
    payload.password = passwordInput.value;
    payload.passwordConfirm = confirmInput.value;
  }
  if (!isFirstTime.value) {
    payload.currentPassword = currentInput.value;
  }

  saving.value = true;
  try {
    const updated = await setCredentials(payload);

    // ⚠️ `setCredentials` 返回的是**后端原始结构**（字段是 avatar_url、username 可能为 null），
    //    而页面里的 `user` 是前端统一加工过的 `CurrentUser`（username 统一成 ''）。
    //    两者不能直接赋值（类型检查会拦，这次也确实拦住了）。
    //    这里只需要把用户名同步过来——反正马上要返回上一页，
    //    没有为了刷新一个字段多打一次 `GET /users/me`。
    if (user.value) {
      user.value = { ...user.value, username: updated.username ?? '' };
    }

    // 清掉三个密码框：密码没必要在界面上多留一秒
    passwordInput.value = '';
    confirmInput.value = '';
    currentInput.value = '';

    uni.showToast({ title: '已保存', icon: 'success' });
    // 回上一页。「我的」和「设置」都在 onShow 里重新拉用户信息，
    // 所以用户名会自动更新，这里不用发全局事件。
    setTimeout(() => uni.navigateBack(), 600);
  } catch (error) {
    // 服务端的提示很具体（"当前密码不正确"/"该用户名已被占用"），原样透给用户
    showError(error);
  } finally {
    saving.value = false;
  }
}

onShow(load);
</script>

<style scoped>
.cred-page {
  min-height: 100vh;
  padding: var(--s-4) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

/* 顶部说明：这一页两种形态差别很大，先说清楚再让用户填 */
.intro {
  margin: 0 var(--s-1) var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}
.intro-title { color: var(--c-text); font-size: 32rpx; font-weight: 500; }
.intro-desc { color: var(--c-text-2); font-size: 24rpx; line-height: 1.6; }

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

/* ⚠️ 输入行必须显式撑满：input 是替换元素，不写宽度它会用"固有宽度"，
   iOS 上会缩成很窄一条（项目里踩过这个坑，见 .field 的同一处注释）。 */
.field-row {
  display: flex;
  align-items: center;
  min-height: 112rpx;
  padding: 0 var(--s-3);
  border-bottom: 2rpx solid var(--c-border);
}
.field-row:last-child { border-bottom: none; }
.field-input {
  display: block;
  width: 100%;
  color: var(--c-text);
  font-size: 29rpx;
}
.field-placeholder { color: var(--c-text-3); }

.field-hint {
  display: block;
  margin: var(--s-1) var(--s-1) 0;
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.5;
}

/* 保存按钮：用主色，和上面那些"只是看看"的条目拉开层级 */
.save-btn {
  margin: var(--s-5) var(--s-1) 0;
  border: none;
  border-radius: var(--r-lg);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  line-height: 88rpx;
}
.save-btn--disabled { background: var(--c-disabled); color: #fff; }
/* uni-app 的 button 默认带一条 ::after 边框，清掉，免得和圆角描边叠出双线 */
.save-btn::after { border: none; }

.page-note {
  display: block;
  margin: var(--s-3) var(--s-1) 0;
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.6;
}
</style>
