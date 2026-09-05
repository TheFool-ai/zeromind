# 订阅管理领域设计

状态：已实现（2026-09-05）。订阅模块已按本文分层，原有平铺模块已移除。

本文记录订阅管理的上下文边界、领域对象、领域方法、依赖关系和实际包结构。
后续调整对象、方法或边界时应同时更新本文。

## 1. 范围与统一语言

订阅管理回答：订阅哪个信息源、是否继续订阅、何时再次轮询，以及最近的抓取状况。

| 术语 | 含义 |
| --- | --- |
| 订阅 Subscription | 一个持续跟踪的信息源配置，具有独立 ID 和生命周期 |
| 订阅地址 FeedAddress | HTTP/HTTPS Feed 地址，或逻辑 RSSHub 路由地址 |
| 健康状态 SubscriptionHealth | 抓取状况及停用状态的有限取值 |
| 轮询 Poll | 对已订阅信息源执行一次检查 |
| 到期认领 ClaimDue | 暂时认领需要轮询的订阅，减少调度器重复派发 |
| OPML 导入 | 从交换格式中提取条目，再逐条执行创建订阅用例 |

当前功能包括创建、列表查询、启用、停用、OPML 预览与导入、抓取状态记录、到期认领。
本轮重构未新增编辑地址、删除订阅、OPML 导出或自定义轮询配置。

## 2. 限界上下文及边界

`subscriptions` 自身是一个限界上下文；领域层、应用层、基础设施层和接口层是它的内部技术分层，
不分别构成限界上下文。下表描述与订阅直接相关的上下文，不是整个 information 应用的完整领域目录。

| 上下文 | 拥有的职责与数据 | 与订阅上下文的关系 |
| --- | --- | --- |
| 订阅管理 `subscriptions` | 订阅配置、启停、地址唯一性、健康状态、轮询时间 | 拥有 `Subscription` 聚合 |
| RSSHub 接入 `rsshub` | 实例配置、激活实例、凭据、逻辑路由到实际请求地址的解析 | 订阅保存逻辑地址；执行抓取时由 RSSHub 接入解析实际地址 |
| 内容采集 `ingestion` | Feed 请求与解析、内容引用、修订、条目去重 | 使用订阅 ID 关联来源；采集结果交给订阅应用层记录成功或失败 |
| 内容分析 `analysis` | 结构化分析、评分、人工修订及分析中的来源快照 | 读取订阅标题和地址等来源信息，不修改订阅状态 |

约束：

- 文章、引用、分析结果、RSSHub 实例不是 `Subscription` 的子实体。
- 跨上下文使用 ID、明确的查询结果和调用契约，不让领域对象持有其他上下文的仓储或 ORM 对象。
- 订阅领域对象不执行 HTTP 请求，不解密 RSSHub 凭据，不操作任务队列。
- OPML 是输入格式。预览、导入是订阅应用用例，不单独建立一个 OPML 限界上下文。
- `bootstrap` 是应用组装和任务入口，不是业务限界上下文。

### 对外契约与应用组装

`public.py` 显式暴露 `FeedAddress`、`SubscriptionService` 和 `SubscriptionView`。

- `ingestion/read_models.py` 和 `analysis/projector.py` 通过 `SubscriptionService.get()`
  读取不可变订阅快照，不再依赖订阅仓储或聚合。
- `rsshub/resolver.py` 和 `ingestion/domain.py` 通过公开的 `FeedAddress.parse(...).value`
  复用地址规范化，不导入订阅内部实现路径。
- `bootstrap/tasks.py` 通过应用服务认领订阅、查询快照和记录抓取成功/失败；
  任务入口仍负责协调 RSSHub 解析、抓取、内容入库与 outbox。
- `bootstrap/app.py` 组装 SQL/内存仓储、XML 解析器、应用服务和 HTTP 路由。
  HTTP、引用读取和分析投影共享同一订阅应用服务，避免出现查询与写入使用不同仓储的情况。
- `SubscriptionView` 只包含不可变标量及元组；对外 `feed_url` 和 `health` 为字符串，
  不暴露聚合的值对象或可变状态。快照不会随着后续保存被原地修改。

技术组装例外：相邻上下文的 ORM 模型为外键注册、Alembic `env.py` 为元数据注册，
仍显式导入 `infrastructure/persistence/subscription_model.py`。
这是持久化元数据关联，不是跨上下文业务代码读取订阅仓储或修改聚合的入口。

## 3. 聚合根、实体和值对象清单

| 分类 | 对象 | 标识与相等性 | 文件 | 实现 |
| --- | --- | --- | --- | --- |
| 聚合根，也是实体 | `Subscription` | 由订阅 ID 标识；同一 ID 的订阅可以随时间改变状态 | `domain/aggregates/subscription.py` | 按 ID 比较相等的 dataclass；不可哈希，修改状态不改变实体身份 |
| 聚合内普通实体 | 无 | 当前没有独立标识和生命周期的子对象 | 不创建空的 `entities/` 目录 | 无 |
| 值对象 | `FeedAddress` | 按规范化后的地址值比较；不可变 | `domain/value_objects/feed_address.py` | 不可变 dataclass；构造和 `parse()` 均执行规范化 |
| 枚举型值对象 | `SubscriptionHealth` | 按枚举值比较；不可变、无独立 ID | `domain/value_objects/subscription_health.py` | 独立文件中的 `StrEnum` |

`Subscription` 不在 `entities/` 中重复定义：聚合根本身就是实体的一种。
`SubscriptionHealth` 保留枚举实现，不为它添加人工 ID 或可变生命周期。

其他字段先保持简单类型：

- `id` 使用 UUID；标题和网站地址使用字符串；分类使用字符串元组。
- ETag、Last-Modified、时间戳和连续失败次数保留为聚合状态。
- 标题去空白与非空校验、分类去空白与去重，暂时由聚合创建方法负责。
- 不仅因为字段存在就包装一个值对象。出现独立规则或复用需求时，再新增对象并补充本清单。

### 不属于领域实体或值对象的类型

| 类型 | 定位 |
| --- | --- |
| `SubscriptionModel` | SQLAlchemy 持久化模型，是聚合的数据库表示，不是第二个领域实体 |
| `SubscriptionRepository` | 仓储接口，不是领域对象 |
| `SubscriptionService` | 应用服务，组织用例、查询和持久化 |
| `OpmlEntry`、`OpmlPreview`、`InvalidOpmlEntry` | OPML 预览/导入 DTO，放应用层 |
| `ImportItemResult`、`ImportResult` | 应用用例结果 DTO |
| HTTP Request/Response 类型 | 接口层协议模型，不放入领域层 |

DTO 即使采用不可变 dataclass，也不因此成为 DDD 值对象；分类取决于业务含义和职责。

## 4. 领域方法与规则

### 4.1 Subscription 聚合根

以下五个方法保留原有职责。`feed_url` 字段为 `FeedAddress`；`create()` 同时接受字符串和地址值对象，并统一转为值对象。

| 方法 | 业务含义 | 主要规则及状态变化 |
| --- | --- | --- |
| `create(feed_url, title, site_url, categories, now)` | 创建订阅 | 校验地址、标题去空白且非空、分类去空白去重；生成 ID；初始启用且健康；首次轮询时间为当前时间 |
| `enable(now)` | 恢复订阅 | `enabled=True`、健康状态为 `healthy`，下次轮询时间设为当前时间，更新修改时间 |
| `disable(now)` | 停用订阅 | `enabled=False`、健康状态为 `disabled`，更新修改时间 |
| `mark_success(now, etag, last_modified, poll_interval)` | 记录一次检查成功 | 更新检查/成功时间及缓存校验信息；失败次数归零；健康状态为 `healthy`；默认 30 分钟后再轮询 |
| `mark_failure(now)` | 记录一次检查失败 | 更新检查时间、累加失败次数；前两次为 `degraded`，第三次起为 `error`；计算退避后的下次轮询时间 |

失败退避公式为 `min(30 × 2^(连续失败次数 - 1), 1440)` 分钟。
HTTP 304 表示检查成功，沿用已有 ETag 和 Last-Modified。

兼容性说明：当前 `enable()` 不清零历史失败次数；成功检查才清零。
`disable()` 不取消已经派发的抓取任务。现有成功/失败方法也不自行判断订阅是否已停用。
因此“停用与在途抓取结果之间的并发一致性”需要单独设计，不能把包迁移描述为已经解决该问题。

封装规则：聚合的业务状态通过领域方法修改；数据库重建对象由 mapper 完成，
不通过 `create()` 重建已有记录，以免重新生成 ID 或重置历史状态。

### 4.2 FeedAddress 值对象

该对象从原地址规范化函数提取，采用不可变实现，一个文件定义一个对象。

| 方法/属性 | 业务含义 | 约束 |
| --- | --- | --- |
| `parse(raw)` | 校验并生成规范化地址对象 | 接受 HTTP、HTTPS、RSSHub 逻辑地址；拒绝已有规则不允许的地址 |
| `value` | 获取规范化地址字符串 | 用于持久化、唯一性检查和接口输出 |
| `is_rsshub` | 判断是否为 RSSHub 逻辑地址 | 只识别地址种类，不选择实例、不拼接访问凭据 |
| 值相等及哈希 | 判断是否代表相同规范化地址 | 基于规范化后的 `value`，不依赖对象内存地址 |

沿用现有 HTTP 地址规范化规则：协议和主机规范化、IDNA 主机转换、去默认端口、
补充空路径、排序查询参数、移除片段、拒绝内嵌用户名密码。
本次补充修复 IPv6 地址的方括号保留，确保地址规范化可重复执行，数据库读取时不会把已保存地址解析坏。

沿用现有 RSSHub 规则：要求有效路由，拒绝用户名密码、端口、片段、空白和路径穿越；
保留路由及查询部分的现有语义。不要擅自将 HTTP 查询排序规则套用到 RSSHub 地址上。

该对象仅进行地址语法与规范化处理。DNS 解析、私网限制和重定向检查属于网络访问实现。

### 4.3 SubscriptionHealth 枚举型值对象

取值为 `healthy`、`degraded`、`error`、`disabled`。
只提供枚举构造、比较及序列化值，不提供 `enable()`、`mark_success()` 等状态修改方法；
状态转换统一由 `Subscription` 负责。

### 4.4 领域服务与领域事件

当前没有独立领域服务或领域事件。当前规则可以由聚合和值对象表达。
`SubscriptionService` 是应用服务；OPML 解析器、定时任务和 SQLAlchemy 仓储都不是领域服务。
轮询/退避规则暂时保留在聚合中；出现多个策略或配置需求后，再决定是否抽出独立对象。

## 5. 应用用例、仓储与一致性

| 应用用例 | 组织方式 |
| --- | --- |
| 创建订阅 | 解析地址 → 查重 → `Subscription.create()` → 仓储保存 |
| 查询列表/来源信息 | 仓储查询 → 返回应用 DTO；跨上下文消费者只获取需要的信息 |
| 启用/停用 | 加载聚合 → `enable()` / `disable()` → 保存 |
| OPML 预览 | 调用解析端口 → 返回有效条目、无效条目、文件内重复数 |
| OPML 导入 | 解析文件 → 对有效条目逐条执行创建用例 → 汇总新增、重复和无效结果 |
| 到期认领 | 应用层调用仓储原子认领，返回调度所需订阅信息 |
| 记录抓取结果 | 加载聚合 → `mark_success()` / `mark_failure()` → 保存 |

`SubscriptionService` 的公开方法如下：

| 方法 | 返回值/职责 |
| --- | --- |
| `create(...)`、`set_enabled(id, enabled)` | 返回保存后的 `SubscriptionView` |
| `get(id)` | 返回快照或 `None` |
| `list()` | 返回订阅快照元组 |
| `claim_due(now, limit, lease)` | 返回本次认领的订阅快照元组 |
| `record_success(id, now, etag, last_modified, poll_interval)` | 加载聚合、记录成功并保存，返回新快照 |
| `record_failure(id, now)` | 加载聚合、记录失败并保存，返回新快照 |
| `preview_opml(data)` | 同步调用解析端口，返回 `OpmlPreview` |
| `import_entries(entries)` | 批量执行创建用例，返回 `ImportResult` |
| `import_opml(data)` | 返回 `(OpmlPreview, ImportResult)`，供 HTTP 汇总无效条目及导入结果 |

应用服务必须注入订阅仓储。启用 OPML 用例时还需注入 `OpmlParser`，默认 HTTP 应用已注入
`XmlOpmlParser`；只进行查询、调度或状态记录的服务组合可以省略解析器。
服务更新不存在的订阅时抛出 `KeyError`；HTTP 接口把启停用例中的该错误转换为 404。

`SubscriptionRepository` 放在领域层，提供 `add`、`get`、`find_by_url`、`list`、`save`、`claim_due`。
`find_by_url` 接收 `FeedAddress`；SQLAlchemy 实现放在基础设施层。仓储按完整聚合进行读写，不为健康状态或地址单独建仓储。

一致性边界：

- 一个订阅是一个聚合，一次启停或抓取结果更新以单个订阅为保存单位。
- “地址不可重复”涉及多个聚合，由应用层预检查和数据库唯一约束共同保证；
  不在聚合方法中访问数据库。并发创建时仍应映射为重复订阅错误。
- OPML 导入当前逐条创建，不是整个文件全有或全无的事务；本次重构保留这一行为。
- `claim_due` 是批量调度所需的仓储原子能力，不是单个聚合的方法。
  当前实现使用 `next_poll_at` 表达认领租期，数据库端通过行锁和 `skip_locked` 避免同时认领；
  该认领行为已保留，它不同于抓取成功后的业务轮询间隔。
- 聚合划分本身不解决并发覆盖。独立的版本控制或租约改造不隐含在本轮目录迁移中。

内存仓储也用于无数据库的服务组合，因此保留在基础设施层。它在写入、读取和认领返回时复制聚合，
调用方必须显式保存修改，避免内存实现与数据库实现拥有不同的对象共享语义。

## 6. 一个对象一个文件的包结构

硬性约定：每个聚合根、实体、值对象都有独立文件，文件名使用对象名称的 snake_case。
禁止用 `entities.py`、`aggregates.py`、`value_objects.py` 聚合多个领域对象。
`__init__.py` 只负责包声明或显式导出，不定义领域类型。
对象私有的辅助函数可以和对象放在同一文件中；新增普通实体时才创建 `entities/`。

```text
apps/information/
├── docs/domains/
│   └── subscriptions.md
├── src/zeromind/subscriptions/
│   ├── __init__.py
│   ├── public.py
│   ├── domain/
│   │   ├── aggregates/
│   │   │   └── subscription.py
│   │   ├── value_objects/
│   │   │   ├── feed_address.py
│   │   │   └── subscription_health.py
│   │   ├── repositories/
│   │   │   └── subscription_repository.py
│   │   └── exceptions/
│   │       └── duplicate_subscription_error.py
│   ├── application/
│   │   ├── subscription_service.py
│   │   ├── dto/
│   │   │   ├── subscription_view.py
│   │   │   ├── opml_entry.py
│   │   │   ├── invalid_opml_entry.py
│   │   │   ├── opml_preview.py
│   │   │   ├── import_item_result.py
│   │   │   └── import_result.py
│   │   ├── ports/
│   │   │   └── opml_parser.py
│   │   └── exceptions/
│   │       └── invalid_opml_error.py
│   ├── infrastructure/
│   │   ├── persistence/
│   │   │   ├── subscription_model.py
│   │   │   ├── subscription_mapper.py
│   │   │   ├── sqlalchemy_subscription_repository.py
│   │   │   └── in_memory_subscription_repository.py
│   │   └── opml/
│   │       └── xml_opml_parser.py
│   └── interfaces/
│       └── http/
│           ├── routes.py
│           └── schemas.py
└── tests/subscriptions/
    ├── domain/
    │   ├── test_subscription.py
    │   └── test_feed_address.py
    ├── application/
    │   ├── test_subscription_service.py
    │   └── test_subscription_import.py
    ├── infrastructure/
    │   ├── test_subscription_repository.py
    │   └── test_xml_opml_parser.py
    └── interfaces/
        └── test_subscription_api.py
```

目录树省略各子包的 `__init__.py`。`SubscriptionView` 是应用查询 DTO。
接口层 `schemas.py` 可以包含多个 HTTP 协议模型，它们不属于聚合根、实体或值对象；
应用 DTO 在此设计中也按对象独立文件存放，便于定位。

依赖方向：

```text
HTTP / 任务入口 → application → domain
infrastructure → domain 仓储接口 + application 端口
bootstrap → 组装以上组件
```

领域层不导入应用层、基础设施层、FastAPI、SQLAlchemy、Celery 或 XML 解析库。
应用层依赖抽象端口，不直接构造具体数据库或解析器。

## 7. 原代码迁移映射与验证

| 重构前代码 | 当前归属 |
| --- | --- |
| `domain.py:Subscription` | `domain/aggregates/subscription.py` |
| `domain.py:SubscriptionHealth` | `domain/value_objects/subscription_health.py` |
| `domain.py:normalize_feed_url` 及地址辅助函数 | `FeedAddress` 的构造逻辑及同文件私有函数 |
| `domain.py:DuplicateSubscriptionError` | `domain/exceptions/duplicate_subscription_error.py` |
| `service.py` | 应用服务和独立的导入结果 DTO |
| `repository.py` | 领域仓储接口、基础设施仓储实现和 mapper |
| `models.py` | `infrastructure/persistence/subscription_model.py` |
| `opml.py` | 应用 DTO、解析端口、解析错误与 XML 解析实现 |
| `api.py` | HTTP 路由与协议模型 |
| `bootstrap/tasks.py` 中订阅状态/认领编排 | 订阅应用层；任务声明和跨上下文流程仍由入口协调 |

本次迁移保留现有 HTTP 路径、响应字段、数据库列和 `init-sql/versions/` 迁移历史，
前端继续消费字符串地址。持久化和 HTTP 边界显式转换 `FeedAddress.value`。

后续回归检查应覆盖：

1. 每个领域对象能由本文直接定位到唯一文件；领域层没有外层框架依赖。
2. 地址规范化兼容现有 HTTP、RSSHub、OPML、采集和解析测试；验证值相等与不可变性。
3. 聚合创建、启停、成功/失败、退避和历史数据重建行为符合文档。
4. 数据库与内存仓储对相同用例表现一致，保留唯一性和到期认领语义。
5. 6 个现有 HTTP 接口、OPML 导入、订阅前端流程和端到端采集分析仍可运行。
6. 修改对象、方法、规则或上下文交互时同步维护本文，不把目标状态写成已实现事实。
