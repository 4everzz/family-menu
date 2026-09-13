import { defineConfig } from 'vite';
import uniModule from '@dcloudio/vite-plugin-uni';

// 当前 UniApp 插件走 alpha 通道，CommonJS / ESM 混合导出，
// 这里做一层兜底：导出本身是函数就直接用，否则取 default。
const uni = typeof uniModule === 'function' ? uniModule : (uniModule as any).default;

export default defineConfig({
  plugins: [uni()],
  server: {
    host: '0.0.0.0',
    port: 5174,
  },
});
