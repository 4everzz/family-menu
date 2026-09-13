<template>
  <view class="page-shell auth-page">
    <view class="auth-card">
      <text class="page-title">登录小家菜单</text>
      <text class="page-copy">登录后才会保存订单记录；不登录也可以先扫码、浏览菜单和加入购物车。</text>
      <button class="primary-button" :loading="authStore.loading" :disabled="authStore.loading" @click="login">微信登录</button>
      <button class="secondary-button" :disabled="authStore.loading" @click="cancel">暂不登录</button>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue';
import { onLoad } from '@dcloudio/uni-app';
import { useAuthStore } from '../../stores/auth';
import { showError } from '../../utils/format';

const authStore = useAuthStore();
const returnTo = ref('');

onLoad((query) => {
  const target = decodeURIComponent(String(query?.returnTo || ''));
  returnTo.value = target.startsWith('/pages/') ? target : '';
});

async function login() {
  try {
    await authStore.loginWithWechat();
    uni.showToast({ title: '登录成功', icon: 'success' });
    setTimeout(() => {
      if (returnTo.value) uni.redirectTo({ url: returnTo.value });
      else uni.navigateBack({ delta: 1 });
    }, 350);
  } catch (error) {
    showError(error.message || '微信登录失败，请稍后重试');
  }
}

function cancel() {
  uni.navigateBack({ delta: 1, fail: () => uni.switchTab({ url: '/pages/menu/index' }) });
}
</script>

<style scoped>
.auth-page { display: flex; align-items: center; min-height: 100vh; padding: 48rpx 32rpx; }
.auth-card { width: 100%; display: flex; flex-direction: column; gap: 24rpx; padding: 40rpx 32rpx; border: 2rpx solid #fee2e2; border-radius: 24rpx; background: #fff; box-shadow: 0 10rpx 26rpx rgba(69, 10, 10, .07); }
.page-title { color: #450a0a; font-size: 42rpx; font-weight: 700; }
.page-copy { color: #78716c; font-size: 27rpx; line-height: 1.65; }
.primary-button, .secondary-button { width: 100%; min-width: 0; height: 92rpx; margin: 0; padding: 0 24rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 700; line-height: 92rpx; box-sizing: border-box; }
.primary-button { background: #dc2626; color: #fff; }
.secondary-button { border: 2rpx solid #fecaca; background: #fff; color: #b91c1c; }
.primary-button[disabled], .secondary-button[disabled] { opacity: .55; }
</style>
