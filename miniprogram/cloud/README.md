# 当前微信云开发数据约定

当前小程序已经接入微信云开发，云环境 ID 为 `cloud1-d2gua37h7753f3812`。

前端通过 `wx.cloud.callFunction` 调用云函数，云函数负责身份校验、订单创建、库存扣减和管理操作。前端不能直接决定管理员权限或直接扣库存。

## 数据集合

| 集合 | 用途 | 当前关键字段 |
| --- | --- | --- |
| `users` | 微信登录用户和角色 | `openId`、`nickname`、`avatarFileId`、`role`、`enabled`、`createdAt` |
| `categories` | 菜品分类 | `id`、`name`、`sort`、`createdAt`、`updatedAt` |
| `dishes` | 菜品和每日库存 | `id`、`name`、`category`、`price`、`description`、`imageFileId`、`enabled`、`dailyStock`、`stock`、`manualSoldOut`、`spiceOptions`、`defaultSpice` |
| `orders` | 顾客订单 | `id`、`ownerUserId`、`ownerOpenId`、`items`、`total`、`remark`、`status`、`createdAtServer` |

## 用户角色

| 角色值 | 含义 | 权限 |
| --- | --- | --- |
| `user` | 普通用户 | 点菜、下单、查看自己的订单 |
| `manager` | 管理员 | 管理菜品、分类和订单 |
| `super_admin` | 超级管理员 | 具有管理员权限，并可管理其他用户角色 |

## 订单状态

当前家庭使用流程只有两步：

```text
制作中 -> 已完成
```

订单创建和库存扣减必须在 `admin-menu` 云函数的事务中完成，避免多人同时下单时把库存扣成负数。

## 图片与时间

- 菜品图片和用户头像保存在微信云存储，数据库只保存 `cloud://` 格式的文件 ID。
- 云函数读取文件 ID 后生成临时访问链接，前端不可长期保存该链接。
- `createdAtServer` 使用云端时间作为排序来源；前端展示时统一转换为北京时间。

## 安全边界

- 小程序前端只负责展示和提交请求，不承担权限判断。
- 管理相关云函数必须从当前微信 OpenID 读取用户角色。
- 不要把管理员密码、AppSecret、云环境密钥或订阅消息密钥写进小程序代码。
