# SUB-001 创建来源

状态：已实现。对应 [应用服务](../../../src/subscription_service/application/subscription_service.py) 的 create。

```mermaid
sequenceDiagram
    actor C as 客户端
    participant H as HTTP API
    participant A as App
    participant D as Subscription / FeedAddress
    participant U as UoW
    participant R as 来源仓储
    participant DB as 数据库
    C->>H: POST 来源
    H->>H: 请求类型、字段校验
    H->>A: create(name,address,categories)
    A->>D: parse + create，规范化并校验
    D-->>A: 默认启用、版本 1 的来源
    A->>U: 打开工作单元
    A->>R: add(source)
    R->>DB: INSERT + flush
    alt 地址唯一约束冲突
        DB-->>R: 唯一冲突
        R-->>A: DuplicateSubscriptionError
        A->>U: 异常退出，回滚并关闭
        H-->>C: 409 subscription_already_exists
    else 插入成功
        A->>U: commit
        U->>DB: COMMIT
        A->>U: 退出并关闭
        A-->>H: 不可变 DTO
        H-->>C: 201 + Location + 详情
    end
```

请求校验失败在进入应用服务前返回 422；领域校验失败发生在打开工作单元前，同样无写入。
其他数据库异常不会伪装成地址重复；提交失败也不能返回创建成功。
没有“先查再插”作为唯一保障，数据库唯一约束处理竞争写入。
