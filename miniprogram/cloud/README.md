# 微信云开发接入准备

当前小程序仍使用本机内存和本机缓存保存购物车与订单。本目录定义了接入微信云开发后需要使用的数据字段和状态名称，尚未创建任何线上资源。

当前开发环境 ID：`cloud1-d2gua37h7753f3812`。

## 需要创建的数据集合

| 集合 | 用途 | 最小字段 |
| --- | --- | --- |
| users | 已注册用户和管理者身份 | role、account、phone、passwordHash、nickname、createdAt |
| categories | 菜品分类 | name、sort、icon、enabled |
| dishes | 菜品信息 | name、price、categoryId、description、image、soldOut、enabled |
| orders | 点餐订单 | ownerKey、items、subtotal、discount、total、remark、status、createdAt |

## 订单状态

```text
submitted -> cooking -> serving -> completed
                    -> cancelled
```

游客订单使用匿名 `ownerKey`，只能查看自己当前微信和当前设备创建的订单。注册用户使用自己的用户编号；管理者账号才能读取全部订单和修改菜品。

## 后续接入顺序

1. 在微信开发者工具创建云开发环境。
2. 创建上述四个集合。
3. 配置集合访问规则。
4. 将菜单读取、创建订单和管理者登录逐步替换为云函数调用。

不要把管理者密码、AppSecret 或云环境密钥写入小程序代码。
