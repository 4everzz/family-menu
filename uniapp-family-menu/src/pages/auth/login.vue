<template>
  <view class="auth-page">
    <!-- 品牌区：登录页是用户见到产品的第一屏，说清楚"这是什么"比放装饰重要 -->
    <view class="brand">
      <text class="brand-title">小家今日吃什么</text>
      <text class="brand-sub">一家人共用的菜谱与冰箱</text>
    </view>

    <!-- 登录 / 注册切换。做成两个大按钮而不是一个"没有账号？去注册"的小链接：
         手机上没有 hover 提示，小链接很容易被忽略。 -->
    <view class="mode-switch">
      <view
        class="mode-item"
        :class="{ active: mode === 'login' }"
        hover-class="tap"
        @click="switchMode('login')"
      >登录</view>
      <view
        class="mode-item"
        :class="{ active: mode === 'register' }"
        hover-class="tap"
        @click="switchMode('register')"
      >注册</view>
    </view>

    <view class="form">
      <view class="form-group">
        <text class="field-label">用户名</text>
        <input
          v-model="username"
          type="text"
          class="field"
          :disabled="submitting"
          placeholder="字母、数字或下划线"
          placeholder-class="field-placeholder"
          :maxlength="USERNAME_MAX_LENGTH"
        />
        <text v-if="isRegister" class="field-tip">
          {{ USERNAME_MIN_LENGTH }}-{{ USERNAME_MAX_LENGTH }} 位，只能用字母、数字、下划线
        </text>
      </view>

      <view class="form-group">
        <text class="field-label">密码</text>
        <input
          v-model="password"
          class="field"
          :password="true"
          :disabled="submitting"
          placeholder="请输入密码"
          placeholder-class="field-placeholder"
          :maxlength="PASSWORD_MAX_LENGTH"
          @confirm="submit"
        />
        <text v-if="isRegister" class="field-tip">
          至少 {{ PASSWORD_MIN_LENGTH }} 位。密码不会以任何形式明文保存。
        </text>
      </view>

      <!--
        确认密码只在注册时出现。
        注册不收昵称、头像这些个人资料——用户想改资料去「我的」页改。
        注册表单每多一个字段，放弃注册的人就多一分；能省则省。
      -->
      <view v-if="isRegister" class="form-group">
        <text class="field-label">确认密码</text>
        <input
          v-model="passwordConfirm"
          class="field"
          :password="true"
          :disabled="submitting"
          placeholder="再输入一次密码"
          placeholder-class="field-placeholder"
          :maxlength="PASSWORD_MAX_LENGTH"
          @confirm="submit"
        />
        <text class="field-tip">两次要一致，避免手滑打错后自己都进不去。</text>
      </view>

      <!-- 错误就地显示在表单里，而不是弹 Toast：Toast 一两秒就没了，
           用户回头想看清到底哪里错了都来不及。 -->
      <view v-if="errorMessage" class="error-box">
        <text class="error-text">{{ errorMessage }}</text>
      </view>

      <view
        class="submit-btn"
        :class="{ disabled: submitting }"
        hover-class="tap"
        @click="submit"
      >{{ submitting ? '请稍候…' : isRegister ? '注册并进入' : '登录' }}</view>

      <!--
        微信一键登录只在微信小程序端出现，其它端会被整段编译掉。
        理由：小程序里它免输入、免记密码，是那个渠道体验最好的方式；
        而 App 端要接微信登录需要微信开放平台的企业认证（个人申请不了），
        H5 端则完全不支持 uni.login。
      -->
      <!-- #ifdef MP-WEIXIN -->
      <view class="divider">
        <view class="divider-line" />
        <text class="divider-text">或</text>
        <view class="divider-line" />
      </view>
      <view
        class="wechat-btn"
        :class="{ disabled: submitting }"
        hover-class="tap"
        @click="submitWechat"
      >微信一键登录</view>
      <!-- #endif -->
    </view>

    <text class="footer-note">
      账号和密码由你自己设置，不需要绑定微信或其他平台。
    </text>
  </view>
</template>

<script setup lang="ts">
/**
 * 登录 / 注册页。
 *
 * 几个刻意的选择：
 *
 * 1. 登录和注册放在同一页、用两个大按钮切换，而不是分成两个页面。
 *    因为这个阶段用户往往两种状态都试一次（先点登录发现没账号，再注册），
 *    同页切换不用来回跳转，也不会在页面栈里叠一层。
 *
 * 2. 前端也做一遍校验，但**只是提前提示**。
 *    真正的闸门在后端：别人绕开界面直接调接口，前端校验一点儿都拦不住。
 *    这里的价值是让用户不必"提交一次才知道哪里填错了"。
 *
 * 3. 密码校验规则只在注册时生效，登录时不做格式检查。
 *    原因和后端一致：规则会变，如果哪天把长度上限改了，
 *    老账号用旧规则注册的密码会连登录都进不去——这是最难查的一类问题。
 *
 * 4. 用户名统一转小写后再提交，和后端存的口径保持一致。
 *    否则用户注册时输入法首字母大写（Tom），登录时输小写（tom）就会登不进去。
 *
 * 5. 注册时密码要输两遍（确认密码），而且**不收集昵称、头像**。
 *    前者是为了让用户当场发现自己打错了——不然设完一个自己都不知道是什么的密码，
 *    下次就再也进不来；后者是因为注册表单每多一个字段，放弃注册的人就多一分，
 *    个人资料等登进去在「我的」页改就行。
 */

import { computed, ref } from 'vue';
import {
  loginWithPassword,
  registerWithPassword,
  type LoginResult,
} from '../../services/auth-api';
// #ifdef MP-WEIXIN
import { loginWithWechat } from '../../services/auth-api';
// #endif

/** 下面几个限制值要与后端保持一致，见 backend/app/models/user.py 与 app/core/password.py */
const USERNAME_MIN_LENGTH = 3;
const USERNAME_MAX_LENGTH = 20;
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 64;

/**
 * 用户名字符集：只允许 ASCII 字母、数字、下划线。
 * 昵称不受这个限制（中文、表情都行）——登录用用户名，展示用昵称，两件事分开。
 */
const USERNAME_RE = new RegExp(`^[A-Za-z0-9_]{${USERNAME_MIN_LENGTH},${USERNAME_MAX_LENGTH}}$`);

type Mode = 'login' | 'register';

const mode = ref<Mode>('login');
const username = ref('');
const password = ref('');
/** 确认密码，只在注册时用到 */
const passwordConfirm = ref('');
const submitting = ref(false);
const errorMessage = ref('');

const isRegister = computed(() => mode.value === 'register');

/** 切换登录/注册。清掉上一次的错误，否则会出现"刚切过来就红着一片"的困惑 */
function switchMode(next: Mode): void {
  if (mode.value === next) return;
  mode.value = next;
  errorMessage.value = '';
  // 两种模式里这两个框的含义不同（登录是"要验证的密码"，注册是"新设的密码"），
  // 清空比留着更清楚，免得用户以为填过的还能用
  password.value = '';
  passwordConfirm.value = '';
}

/**
 * 提交前的本地校验。
 * @returns 有问题时返回给用户看的说明；没问题返回空字符串
 */
function validate(
  cleanedUsername: string,
  cleanedPassword: string,
  cleanedPasswordConfirm: string,
): string {
  if (!cleanedUsername) return '请填写用户名';

  // 登录模式下不检查用户名的格式：格式是"注册时该满足的条件"，
  // 登录只要原样拿去比对就行。这里只做一次宽松的长度上限，防止误输入一长串。
  if (isRegister.value) {
    if (!USERNAME_RE.test(cleanedUsername)) {
      return `用户名需为 ${USERNAME_MIN_LENGTH}-${USERNAME_MAX_LENGTH} 位字母、数字或下划线`;
    }
    if (cleanedPassword.length < PASSWORD_MIN_LENGTH) {
      return `密码至少 ${PASSWORD_MIN_LENGTH} 位`;
    }
    if (cleanedPassword.length > PASSWORD_MAX_LENGTH) {
      return `密码最多 ${PASSWORD_MAX_LENGTH} 位`;
    }
    if (cleanedPassword === cleanedUsername) {
      return '密码不能与用户名相同';
    }
    // 确认密码：本地先比一次，让用户当场发现自己打错了。
    // 后端还会再比一次——那才是真正的闸门，这里只是提前提示。
    if (!cleanedPasswordConfirm) return '请再输入一次密码';
    if (cleanedPassword !== cleanedPasswordConfirm) return '两次输入的密码不一致';
  }

  if (!cleanedPassword) return '请填写密码';
  return '';
}

/**
 * 登录成功后的收尾：提示 + 返回上一页。
 *
 * 为什么要延迟再返回？因为 toast 是绑在当前页上的，
 * 立刻返回会把它一起带走，用户只看到页面跳了一下，不知道成没成功。
 */
function leaveAfterSuccess(message: string): void {
  uni.showToast({ title: message, icon: 'none', duration: 600 });
  setTimeout(() => {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      uni.navigateBack();
    } else {
      // 理论上不会走到这里（登录页总是被 navigateTo 打开的），
      // 兜底回首页标签页，别把用户留在登录页上
      uni.switchTab({ url: '/pages/menu/index' });
    }
  }, 600);
}

async function submit(): Promise<void> {
  if (submitting.value) return;

  // 前后都去掉空格：手机输入法和复制粘贴很容易在末尾带一个看不见的空格
  const cleanedUsername = username.value.trim().toLowerCase();
  const cleanedPassword = password.value.trim();
  const cleanedPasswordConfirm = passwordConfirm.value.trim();

  const problem = validate(cleanedUsername, cleanedPassword, cleanedPasswordConfirm);
  if (problem) {
    errorMessage.value = problem;
    return;
  }

  errorMessage.value = '';
  submitting.value = true;

  const registering = isRegister.value;

  try {
    let result: LoginResult;
    if (registering) {
      // 注册只提交账号信息（用户名 + 密码 + 确认密码）。
      // 昵称、头像这些个人资料一律登录后去「我的」页改。
      result = await registerWithPassword(
        cleanedUsername,
        cleanedPassword,
        cleanedPasswordConfirm,
      );
      // 注册成功就等于登录成功（后端直接发了令牌），不用让用户再输一遍
      username.value = result.user.username || cleanedUsername;
    } else {
      result = await loginWithPassword(cleanedUsername, cleanedPassword);
    }

    // 明文密码用完就丢掉，别让它留在页面数据里
    password.value = '';
    passwordConfirm.value = '';
    leaveAfterSuccess(registering ? '注册成功' : '登录成功');
  } catch (error) {
    // 后端返回的消息本身就是给用户看的（例如"该用户名已被占用，换一个试试"），
    // 这里原样显示；只有拿到非预期错误时才兜一句通用文案。
    errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试';
  } finally {
    submitting.value = false;
  }
}

// #ifdef MP-WEIXIN
/**
 * 微信一键登录（只在小程序端存在）。
 *
 * 走的是"静默登录"：uni.login() 拿临时 code，用户不需要点任何授权，也看不到微信的弹窗。
 * 后端拿 code 换 openid，第一次来的会自动建号——这类账号暂时没有用户名和密码，
 * 只能从微信进来（将来可以在「我的」里补设一套账号密码，两端就通了）。
 */
async function submitWechat(): Promise<void> {
  if (submitting.value) return;

  errorMessage.value = '';
  submitting.value = true;
  try {
    await loginWithWechat();
    password.value = '';
    leaveAfterSuccess('登录成功');
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '微信登录失败，请稍后重试';
  } finally {
    submitting.value = false;
  }
}
// #endif
</script>

<style scoped>
.auth-page {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding: var(--s-6) var(--s-3) calc(var(--s-6) + env(safe-area-inset-bottom));
  box-sizing: border-box;
}

.brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--s-2);
  margin-bottom: var(--s-6);
}
.brand-title { color: var(--c-text); font-size: 44rpx; font-weight: 500; }
.brand-sub { color: var(--c-text-2); font-size: 24rpx; }

/* 登录/注册切换：两个等宽的整块，比小链接好点得多（手机上没有 hover 提示） */
.mode-switch {
  display: flex;
  gap: 8rpx;
  padding: 8rpx;
  border-radius: var(--r-pill);
  background: var(--c-muted);
}
.mode-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 触摸目标下限：88rpx（44 逻辑像素，约一根手指的宽度） */
  min-height: var(--touch-min);
  border-radius: var(--r-pill);
  color: var(--c-text-2);
  font-size: 28rpx;
}
.mode-item.active {
  background: var(--c-surface);
  color: var(--c-primary);
  font-weight: 500;
  box-shadow: var(--shadow-card);
}

.form {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin-top: var(--s-4);
}
.form-group { display: flex; flex-direction: column; gap: var(--s-1); }
.field-label { color: var(--c-text-2); font-size: 24rpx; }
.field {
  height: var(--touch-min);
  padding: 0 var(--s-3);
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 29rpx;
  box-sizing: border-box;
}
:deep(.field-placeholder) { color: var(--c-text-3); font-weight: 400; }
.field-tip { color: var(--c-text-3); font-size: 22rpx; line-height: 1.5; }

.error-box {
  padding: var(--s-2) var(--s-3);
  border: 2rpx solid var(--c-danger-border);
  border-radius: var(--r-md);
  background: var(--c-danger-bg);
}
.error-text { color: var(--c-danger-text); font-size: 24rpx; line-height: 1.6; }

.submit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  margin-top: var(--s-1);
  border-radius: var(--r-md);
  background: var(--c-primary);
  color: #fff;
  font-size: 30rpx;
  font-weight: 500;
}
.submit-btn.disabled { background: var(--c-disabled); }

/* 分隔线用两个 flex 撑开的细线夹一个"或"，不用伪元素：
   小程序对伪元素 + 绝对定位的支持时好时坏，能用普通元素就别赌它 */
.divider { display: flex; align-items: center; gap: var(--s-2); }
.divider-line { flex: 1; height: 2rpx; background: var(--c-border); }
.divider-text { color: var(--c-text-3); font-size: 22rpx; }

/* 微信登录按钮刻意做成中性的描边样式，而不是微信绿：
   一是避免为一个尚未定去留的渠道单独引入一个色值，
   二是它只是备选入口，不该和主按钮抢视觉重心 */
.wechat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--touch-min);
  border: 2rpx solid var(--c-border-strong);
  border-radius: var(--r-md);
  background: var(--c-surface);
  color: var(--c-text);
  font-size: 28rpx;
}
.wechat-btn.disabled { color: var(--c-text-3); }

.footer-note {
  display: block;
  margin-top: var(--s-5);
  color: var(--c-text-3);
  font-size: 22rpx;
  line-height: 1.7;
  text-align: center;
}
</style>
