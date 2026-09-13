import { createSSRApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import './uni.scss';

/**
 * 小程序入口工厂函数。
 * uni-app 运行时要求导出一个 createApp 函数，返回 { app } 结构后由框架负责挂载，
 * 不能在这里手动 app.mount()，否则小程序端会白屏。
 */
export function createApp() {
  const app = createSSRApp(App);
  app.use(createPinia());
  return { app };
}
