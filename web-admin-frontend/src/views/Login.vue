<script setup>
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { callApi } from '../api.js';
import { auth } from '../store.js';

const router = useRouter();
const route = useRoute();

const username = ref('');
const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
  error.value = '';
  if (!username.value.trim() || !password.value) {
    error.value = '请输入账号和密码';
    return;
  }
  loading.value = true;
  const result = await callApi('login', {
    username: username.value.trim(),
    password: password.value,
  }, { withToken: false });
  loading.value = false;

  if (result.ok) {
    auth.set(result.token, result.username);
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : null;
    router.replace(redirect || { name: 'overview' });
  } else {
    error.value = result.message || '登录失败';
  }
}
</script>

<template>
  <div class="login">
    <div class="login-panel">
      <div class="login-brand">
        <div class="brand-mark">小家</div>
        <div>
          <div class="brand-name">小家菜单</div>
          <div class="brand-sub">平台控制台</div>
        </div>
      </div>

      <h2 class="login-title">登录后台</h2>
      <p class="login-lead">用平台超级管理员账号登录，管理店铺、授权与跨店数据。</p>

      <form class="login-form" @submit.prevent="submit">
        <div class="field">
          <label for="u">账号</label>
          <input id="u" class="input" v-model="username" autocomplete="username" placeholder="超级管理员账号" />
        </div>
        <div class="field">
          <label for="p">密码</label>
          <input id="p" class="input" v-model="password" type="password" autocomplete="current-password" placeholder="登录密码" />
        </div>

        <p v-if="error" class="notice notice-error">{{ error }}</p>

        <button class="btn btn-primary login-submit" type="submit" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>
    </div>

    <p class="login-note">仅限授权的平台管理员使用</p>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px;
  background:
    radial-gradient(1100px 520px at 82% -8%, #e7efeb 0%, rgba(231,239,235,0) 60%),
    radial-gradient(900px 480px at 6% 108%, #e9efe9 0%, rgba(233,239,233,0) 55%),
    var(--canvas);
}
.login-panel {
  width: 100%;
  max-width: 396px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 12px 44px rgba(24, 33, 28, 0.10);
  padding: 30px 30px 32px;
}
.login-brand { display: flex; align-items: center; gap: 12px; margin-bottom: 26px; }
.brand-mark {
  width: 44px; height: 44px; border-radius: 12px;
  background: linear-gradient(150deg, var(--accent), #3f8f75);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 700;
}
.brand-name { font-weight: 650; font-size: 16px; }
.brand-sub { font-size: 12.5px; color: var(--muted); margin-top: 1px; }

.login-title { font-size: 21px; font-weight: 680; letter-spacing: -0.01em; }
.login-lead { color: var(--muted); font-size: 13.5px; margin-top: 6px; line-height: 1.55; }

.login-form { display: flex; flex-direction: column; gap: 15px; margin-top: 22px; }
.login-submit { width: 100%; height: 42px; margin-top: 4px; }

.login-note { color: var(--muted); font-size: 12.5px; }
</style>
