import { defineStore } from 'pinia';
import { callAuth } from '../services/auth';
import { getStorage, setStorage, removeStorage } from '../utils/storage';

const USER_KEY = 'uni_family_user';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: getStorage(USER_KEY, null),
    loading: false,
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.user),
  },
  actions: {
    restore() {
      this.user = getStorage(USER_KEY, null);
    },
    async refresh() {
      this.loading = true;
      try {
        const result = await callAuth('getCurrentUser');
        this.user = result.user || result.data || null;
        if (this.user) setStorage(USER_KEY, this.user);
        else removeStorage(USER_KEY);
        return this.user;
      } finally {
        this.loading = false;
      }
    },
    async loginWithWechat() {
      this.loading = true;
      try {
        const result = await callAuth('loginWithWechat');
        if (!result.ok || !result.user) throw new Error(result.message || '微信登录失败');
        this.user = result.user;
        setStorage(USER_KEY, result.user);
        return result.user;
      } finally {
        this.loading = false;
      }
    },
    clear() {
      this.user = null;
      removeStorage(USER_KEY);
    },
  },
});
