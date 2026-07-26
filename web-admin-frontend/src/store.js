import { reactive } from 'vue';
import { TOKEN_KEY, USERNAME_KEY } from './config.js';

// 极简的登录态：token + 用户名，持久化到 localStorage，刷新不掉线。
export const auth = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  username: localStorage.getItem(USERNAME_KEY) || '',

  get isLoggedIn() {
    return Boolean(this.token);
  },

  set(token, username) {
    this.token = token || '';
    this.username = username || '';
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USERNAME_KEY, this.username);
    } else {
      this.clear();
    }
  },

  clear() {
    this.token = '';
    this.username = '';
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  },
});
