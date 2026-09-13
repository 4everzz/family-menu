import { defineConfig } from 'vite';
import uniModule from '@dcloudio/vite-plugin-uni';

// 兼容当前 UniApp 插件的 CommonJS/ESM 混合导出方式
const uni = typeof uniModule === 'function' ? uniModule : uniModule.default;

export default defineConfig({
  plugins: [uni()],
  server: {
    host: '0.0.0.0',
    port: 5174,
  },
});
