# 订阅源管理 HTTP API

提供来源管理和 OPML 导入接口，不执行网络访问或调度。创建默认启用，启用不代表立即抓取。
启动方式见 [本地开发](../operations/local-development.md)。交互文档位于 `/api/docs`，OpenAPI 位于 `/api/openapi.json`。

## 接口

公共前缀 `/api/v1/subscriptions`：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | 公共前缀 | 手动创建，返回 201 和 Location |
| GET | 公共前缀 | 列表，支持 enabled、limit、offset |
| GET | `/{id}` | 获取详情 |
| PATCH | `/{id}` | 修改名称、分类和地址 |
| POST | `/{id}/enable` | 幂等启用 |
| POST | `/{id}/disable` | 幂等关闭 |
| POST | `/import/opml` | 批量导入，已有来源跳过；独立契约见 [OPML API](opml-api.md) |

除创建外成功返回 200。暂无删除接口。列表默认 limit=100、offset=0，limit 范围 1～1000；
响应为 `{"items": [...], "limit": 100, "offset": 0}`，不计算总数。

创建示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"name":"示例订阅","feed_address":"https://example.com/feed.xml","categories":["技术"]}'
```

创建必填 name、feed_address；categories 可省略。名称去除首尾空白，分类去空白并去重。
地址支持 HTTP/HTTPS 和 `rsshub://`；只验证地址格式，不检测来源是否可访问。RSSHub 部署连接尚未接入。

PATCH 示例请求体：

```json
{"name":"新的名称","categories":[],"expected_configuration_version":1}
```

只更新提供的字段；空分类数组表示清空。拒绝空修改、显式 null 和未知字段。
启停可以不带请求体，或传 `{"expected_configuration_version":1}`。

## 返回字段

| 字段 | 作用 |
| --- | --- |
| id | 订阅源 UUID |
| name | 展示名称 |
| feed_address | 规范化后的来源地址 |
| categories | 分类数组 |
| enabled | 是否启用 |
| configuration_version | 配置版本，供客户端防止旧数据覆盖新数据 |
| address_version | 地址版本，地址变更时递增 |
| last_successful_fetch_at | 最近成功获取时间，尚未获取时为 null |
| created_at / updated_at | UTC 创建时间、配置更新时间 |

不返回 site_url、数据库内部乐观锁版本、ETag 或 Last-Modified。
相同配置和重复启停不递增配置版本。同时修改名称/分类和地址可能递增两次，版本不是请求计数。

## 事务与错误

应用服务依赖工作单元接口，不依赖 HTTP 或 SQLAlchemy；返回不可变 DTO。
单条管理用例显式提交，失败整体回滚；查询不触发抓取。OPML 按来源逐项提交，不是整批事务。规范化地址由数据库唯一约束查重。
可选 expected_configuration_version 必须为正整数，与当前配置不符返回 409。
即使未提供客户端版本，仓储仍进行事务级乐观锁检查。

错误格式为 `{"detail":{"code":"...","message":"..."}}`，请求校验失败还包含 fields。

| 状态 | code | 含义 |
| --- | --- | --- |
| 404 | subscription_not_found | 来源不存在 |
| 409 | subscription_already_exists | 地址重复 |
| 409 | subscription_version_conflict | 配置版本过期或并发写冲突 |
| 422 | invalid_request | 请求字段、类型或范围非法 |
| 422 | invalid_subscription | 领域规则校验失败 |

校验错误不回显完整输入，避免误填的地址凭据泄露。当前不包含鉴权，勿直接暴露公网。
