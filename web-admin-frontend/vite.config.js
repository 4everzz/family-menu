import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// base: './' 让打包后的 dist 用相对路径引用资源，
// 方便直接上传到云开发「静态网站托管」的任意目录下都能打开。
export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    port: 5173,
  },
});
