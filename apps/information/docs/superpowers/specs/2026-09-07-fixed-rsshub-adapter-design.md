# 固定 RSSHub 适配器设计

**状态：** 已于 2026-09-07 在对话中确认

## 1. 目标

将 RSSHub 支持从一个运行时可管理的业务模块，简化为固定的部署依赖。ZeroMind
继续接受与具体实例无关的 `rsshub://` 订阅地址，但统一通过部署配置提供的一个
RSSHub 基础地址完成解析。

本次调整移除多实例注册、实例激活、数据库凭据和 RSSHub 管理界面。普通
HTTP/HTTPS 订阅、OPML 支持、Feed 轮询、内容采集和下游分析行为保持不变。

## 2. 部署模型

项目自带的 Compose 部署负责运行一个私有 RSSHub 服务，地址为
`http://rsshub:1200`。后端 Worker 通过以下配置获得该地址：

```text
ZEROMIND_RSSHUB_BASE_URL=http://rsshub:1200
```

`TWITTER_AUTH_TOKEN`、Cookie 和代理等 RSSHub 上游来源凭据，继续作为 `rsshub`
容器自身的环境变量。ZeroMind 不读取、不保存、不加密、不暴露，也不管理这些凭据。

RSSHub 服务继续只对 Compose 内部网络开放，不向宿主机发布端口。
`ZEROMIND_RSSHUB_PRIVATE_HOSTS=rsshub` 继续作为网络策略的明确白名单，允许定时
Feed 抓取任务访问 Compose 内部的 RSSHub DNS 名称。

## 3. 架构

RSSHub 地址解析成为订阅模块的基础设施职责：

```text
Subscription.feed_url
  rsshub://twitter/user/example
          |
          v
FixedRSSHubResolver
  从 Settings 读取基础地址
          |
          v
http://rsshub:1200/twitter/user/example
          |
          v
FeedClient -> Ingestion -> Outbox -> 分析工作流
```

解析器位于 `subscriptions` 包的基础设施层，因为它负责将订阅模块支持的地址转换成
可以实际抓取的 HTTP URL。它不再拥有仓储、应用服务、ORM 模型或运行时管理 API。

任务组装层直接使用 `Settings.rsshub_base_url` 构造解析器。应用启动过程不再创建
RSSHub 管理服务，也不再注册 RSSHub HTTP 路由。

## 4. 配置契约

`Settings` 新增：

```python
rsshub_base_url: str = "http://rsshub:1200"
```

该值必须是包含主机名的绝对 HTTP 或 HTTPS URL。允许包含路径前缀，但不允许包含
用户名密码、查询参数、片段、空白字符或路径穿越片段。拼接路由前会移除末尾斜杠。

即使默认值与内置服务一致，Compose 仍会显式传入
`ZEROMIND_RSSHUB_BASE_URL`。使用其他固定 RSSHub 部署的运维人员只需覆盖这个环境
变量。

基础地址配置无效时，Worker 构造解析器就会失败。普通 HTTP/HTTPS 订阅不需要
RSSHub 转换，解析器会原样返回对应地址。

## 5. 解析行为

固定解析器保留现有对外订阅契约：

- HTTP 和 HTTPS Feed 地址原样返回。
- `rsshub://` 地址继续通过 `FeedAddress` 校验和规范化。
- 地址中的路由和非认证查询参数会拼接到配置的基础地址之后。
- 地址中携带的 `key` 和 `code` 查询参数会被移除，避免将凭据保存进订阅记录或夹带进请求。
- ZeroMind 不再生成 Access Key 或 MD5 Code。

示例：

```text
rsshub://twitter/user/vista8
  -> http://rsshub:1200/twitter/user/vista8

rsshub://twitter/user/vista8?mode=full&key=secret
  -> http://rsshub:1200/twitter/user/vista8?mode=full
```

解析器是确定性的，不执行 I/O。轮询流程继续使用 `FeedClient` 现有的网络策略、重定向
校验、超时和响应体大小限制。

## 6. 移除的产品能力

移除以下运行时 RSSHub 管理能力：

- RSSHub 实例领域对象和认证模式；
- 凭据加密和数据库存储；
- 内存与 SQLAlchemy RSSHub 仓储；
- 实例创建、查询、更新、激活和删除服务；
- `/api/v1/rsshub/instances` 接口；
- `/rsshub` 前端页面、导航入口、客户端类型和对应 UI 测试；
- `RSSHubInstanceService` 的启动组装和依赖注入。

继续保留 `rsshub://` 格式、订阅页面提示、`FeedAddress` 校验、OPML 处理和基于
RSSHub 的 Feed 轮询。

## 7. 数据库迁移

新增一个前向 Alembic 迁移，删除已经废弃的 `rsshub_instances` 表及其部分唯一索引。
已有迁移历史保持不变，保证已经部署的数据库可以正常升级。

该迁移会有意删除旧的 RSSHub 实例记录：新的部署配置已经取代这些记录，旧记录在新
模型中没有合理的迁移目标。降级迁移可以重新建立原来的空表结构，但不能恢复已经删除
的实例数据。

Alembic 元数据注册不再导入已删除的 RSSHub ORM 模型。

## 8. 错误处理与安全

- 无效的 `ZEROMIND_RSSHUB_BASE_URL` 会在抓取前抛出稳定的配置 `ValueError`。
- 格式错误的 `rsshub://` 地址继续由 `FeedAddress` 在创建订阅或预览 OPML 时拒绝。
- RSSHub 抓取失败继续进入现有的订阅失败计数和指数退避流程。
- 上游来源凭据始终隔离在 RSSHub 容器内，不会由 ZeroMind API 返回。
- 固定的私有主机只对白名单内的定时 Feed 抓取开放。

## 9. 文档与运维

项目 README 和订阅领域文档会将 RSSHub 描述为固定部署适配器。安装说明不再要求用户
先在界面中注册实例，而是说明 Compose 会自动启动 RSSHub，且来源专用环境变量应配置
在 RSSHub 服务上。

历史实施计划和规格文档作为旧决策记录保留，不进行追溯修改。当前权威文档会更新为
新的实际行为。

## 10. 测试

测试覆盖以下内容：

- 基础地址规范化，以及对不安全配置的拒绝；
- HTTP/HTTPS Feed 地址原样通过；
- `rsshub://` 地址的确定性解析，包括路径前缀和查询参数保留；
- 移除地址中携带的 `key` 和 `code` 参数；
- 轮询任务使用由配置构造的解析器；
- RSSHub API 路由、前端导航和管理页面已经移除；
- 数据库升级删除旧表，降级重新建立旧表结构；
- 渲染后的 Compose 配置包含固定基础地址和私有 RSSHub 服务；
- 现有订阅、OPML、网络策略、Feed 轮询和前端回归测试。

## 11. 非目标

本次调整不增加：

- 多个 RSSHub 实例；
- 运行时实例切换或健康管理；
- 故障转移或负载均衡；
- 按订阅选择 RSSHub 实例；
- 由 ZeroMind 管理的 RSSHub 访问认证；
- 对外公开的 RSSHub 端口；
- 通过界面动态编辑部署配置。
