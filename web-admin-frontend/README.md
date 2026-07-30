# 小家菜单 · 平台超级管理员后台

给平台**超级管理员**使用的内部后台：建店、启停店铺、跨店指派一级/二级管理员、用户管理、跨店订单监管、经营报表、CSV 导出与数据备份。店铺日常现场管理保留在小程序内，避免把超管功能挤进顾客点餐界面。

- 技术：Vue 3 + Vite，纯 CSS，依赖只有 `vue` / `vue-router`，构建产物是纯静态文件。
- 后端：微信云开发云函数 `web-admin`（通过「HTTP 访问服务」暴露）。前端只认一个后台地址，日后后端迁走只改这一处。

## 目录

```
web-admin-frontend/
├─ index.html
├─ vite.config.js
├─ src/
│  ├─ config.js        ← 唯一要改的地方：填后台 HTTP 地址
│  ├─ api.js           ← 统一请求封装（POST { action, token, ... }）
│  ├─ store.js         ← 登录态（token 存 localStorage）
│  ├─ router.js        ← 路由 + 登录守卫（hash 模式）
│  ├─ styles.css       ← 设计令牌与全局样式
│  ├─ App.vue
│  ├─ components/AppLayout.vue   ← 侧栏 + 顶栏外壳
│  └─ views/
│     ├─ Login.vue     ← 登录
│     ├─ Overview.vue  ← 跨店总览
│     ├─ Shops.vue     ← 店铺管理
│     ├─ Members.vue   ← 管理员授权
│     ├─ Users.vue     ← 平台用户管理
│     ├─ Orders.vue    ← 跨店订单监管与导出
│     ├─ Reports.vue   ← 经营报表
│     └─ Backups.vue   ← 店铺数据备份
```

## 第一步：填后台地址

编辑 `src/config.js`，把 `API_BASE` 改成你在云开发控制台「HTTP 访问服务」里为 `web-admin` 云函数分配的完整公网地址，例如：

```js
export const API_BASE = 'https://你的环境.service.tcloudbase.com/web-admin';
```

## 第二步：本地运行 / 打包

> 如果这个目录里已经有一个 `node_modules` 文件夹，请**先手动删除它**再安装（之前在 Linux 沙盒里装了一半，不能用）。

```bash
npm install      # 安装依赖
npm run dev      # 本地预览：http://localhost:5173
npm run build    # 打包，产物在 dist/
```

## 第三步：部署到云开发静态托管

1. `npm run build` 生成 `dist/`。
2. 云开发控制台 → 静态网站托管 → 进入已有 Web 应用，覆盖上传 `dist/` 内的全部文件（含 `index.html` 和 `assets/`）。不需要删除或重新创建应用。
3. 访问静态托管分配的域名即可打开后台；更新后用 `Ctrl + F5` 强制刷新浏览器缓存。
4. 重新部署 `web-admin` 云函数后，确认其 `ALLOWED_ORIGINS` 只包含正式静态托管域名和必要的本地开发端口，避免使用 `*`。

## 登录

用之前 `setup` 建好的超管账号密码登录。token 有效期 2 小时，过期自动回到登录页。

完整发布、备份和故障恢复流程见 [小程序部署与恢复手册](../miniprogram/DEPLOYMENT_AND_RECOVERY.md)。
