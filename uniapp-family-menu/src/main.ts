import { createSSRApp } from 'vue';
import App from './App.vue';
import './uni.scss';

/**
 * 应用入口工厂函数。
 * uni-app 运行时要求导出一个 createApp 函数，返回 { app } 结构后由框架负责挂载，
 * 不能在这里手动 app.mount()，否则小程序端会白屏。
 *
 * 不再引入 Pinia：家庭版没有全局状态，各页面直接调 services/ 下的接口。
 * （原先装 Pinia 只是为商家版那三个 store 服务，它们已随死代码一起删除。）
 */
export function createApp() {
  const app = createSSRApp(App);
  return { app };
}
