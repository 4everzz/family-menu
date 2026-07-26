# web-admin 网页后台 联调清单

部署完 `web-admin` 云函数后，按下面顺序操作。集合 `web_admins`、`web_sessions` 会在首次写入时自动创建，不用手动建。

## 第 1 步：建超管账号（只做一次）

**最简单的方式**：微信开发者工具 → 云开发 → 云函数 → `web-admin` → 右键「云端测试 / 本地调试」，在测试参数里填：

```json
{ "action": "setup", "username": "你的账号", "password": "你自己设的密码" }
```

- 账号 3~32 位，密码至少 8 位。
- 返回 `{ "ok": true, "username": "..." }` 即成功。
- 成功后这个入口会自动关闭（再调返回 `ALREADY_INITIALIZED`），别人无法再注册。
- 密码只存哈希，我这边也看不到，务必自己记牢。

> 这一步不需要 HTTP 访问服务，用云端测试直接调即可。

## 第 2 步：开通 HTTP 访问服务（给网页前端用）

云开发控制台 → 当前环境 → **HTTP 访问服务**（或叫「访问服务 / HTTP 触发」）：

1. 新增一个路径，例如 `/web-admin`，云函数选 `web-admin`。
2. 记下分配的公网访问地址，形如
   `https://你的环境.service.tcloudbase.com/web-admin`。
3. 这个地址就是前端所有请求的目标 URL（POST + JSON）。

## 第 3 步：登录拿 token

对上面的地址发 POST：

```json
{ "action": "login", "username": "你的账号", "password": "你的密码" }
```

返回：

```json
{ "ok": true, "token": "……", "expiresAt": "……", "username": "……" }
```

之后所有业务接口都在 body 里带上这个 `token`。会话有效期 2 小时，过期重新 `login`。

## 第 4 步：业务接口速查（都要带 token）

请求体统一是 `{ "action": "...", "token": "...", ...参数 }`。

| action | 参数 | 作用 |
| --- | --- | --- |
| `me` | 无 | 校验 token、返回当前账号 |
| `listShops` | 无 | 全部店铺 + 每店一级/二级人数 |
| `createShop` | `name` | 建店，返回一次性 `initialShopCode` |
| `setShopEnabled` | `shopId`, `enabled`(bool) | 停用/启用店铺 |
| `searchUsers` | `keyword`，可选 `shopId` | 按昵称/systemId/ID 搜用户 |
| `listShopMembers` | `shopId` | 某店的一级/二级管理员 |
| `grantRole` | `shopId`, `userId`, `role`(`store_owner`/`store_staff`) | 授予一级/二级 |
| `revokeRole` | `shopId`, `userId` | 撤销该店权限 |
| `getPlatformOverview` | 无 | 跨店总览（店数/用户/今日订单营业额/Top10） |

**典型流程**：`createShop` 建店 → `searchUsers` 找到店主的微信用户 → `grantRole`（role=`store_owner`）把他设为一级 → 之后店主就能在小程序里管理这家店、再自行授权二级。

## 第 5 步：正式上线前的安全收尾（#14）

- `index.js` 里 `ALLOWED_ORIGINS` 目前是 `['*']`（仅供联调）。前端静态托管部署后，把它改成托管的实际域名，重新部署，收紧 CORS。
- 确认所有业务接口都在会话校验之后（`setup`/`login`/`logout` 之外一律需 token）。
- 妥善保管超管账号密码；如需改密，后续可加一个「修改密码」接口。

## 现在可以做的

1. 完成第 1 步建号、第 2 步开 HTTP 服务、第 3 步 login 验证能拿到 token。
2. 拿到公网地址后告诉我，我就开始用 Soybean Admin 搭前端三页（登录 / 店铺管理 / 授权 / 总览），把上面接口接上。
