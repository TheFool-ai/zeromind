# SUB-006 / SUB-007 条目与修订

状态：以下领域方法和仓储操作已实现；图中的“调用者”是内部调用示例或测试，不是已存在的采集应用服务。

## 首次发现

```mermaid
sequenceDiagram
    participant C as 内部调用者
    participant D as SubscriptionItem
    participant U as UoW
    participant R as 条目仓储
    participant DB as 数据库
    C->>D: discover(source_id,identity,metadata,observed_at)
    D-->>C: item + revision 1
    C->>U: 打开工作单元
    C->>R: add(item,revision)
    R->>R: 校验首版本与条目匹配
    R->>DB: INSERT 条目 + flush
    R->>DB: INSERT 修订 1 + flush
    alt 任一步失败
        R-->>C: 唯一冲突、外键或其他异常
        C->>U: 异常退出，回滚全部写入
    else 全部成功
        C->>U: commit 并退出
        U->>DB: COMMIT
    end
```

同来源身份重复是 DuplicateItemError，缺失来源的外键错误不会被当作重复处理。

## 再次观察

```mermaid
sequenceDiagram
    participant C as 内部调用者
    participant U as UoW
    participant R as 条目仓储
    participant D as SubscriptionItem
    participant DB as 数据库
    C->>U: 打开工作单元
    C->>R: get / find_by_identity
    C->>R: get_revision(item_id,current_revision)
    R-->>C: 条目与当前不可变修订
    C->>D: observe(current_revision,metadata,observed_at)
    D->>D: 校验所属条目、版本、时间，比较规范化元数据
    alt 内容相同
        D-->>C: None；只更新 last_seen_at
        C->>R: save(item)
        R->>DB: 乐观 UPDATE + flush
    else 内容改变
        D-->>C: 新修订；推进 current_revision 与 last_seen_at
        C->>R: save(item,new_revision)
        R->>DB: 先乐观 UPDATE 条目 + flush
        R->>DB: 再 INSERT 新修订 + flush
    end
    C->>U: 无异常才 commit 并退出
    U->>DB: COMMIT
```

观察校验失败不改变聚合；保存期间任一步失败则退出回滚，不执行图末的 commit。
版本推进必须伴随新修订，新修订必须连续，历史版本不可覆盖。无变化也必须 save 才能保存观察时间。

## 查询条目与历史

```mermaid
sequenceDiagram
    participant C as 内部调用者
    participant U as UoW
    participant R as 条目仓储
    participant DB as 数据库
    C->>U: 打开工作单元
    C->>R: list_by_subscription / get_revision / list_revisions
    R->>DB: 限定来源或条目查询，按需分页
    DB-->>R: 持久化行
    R-->>C: 领域条目、不可变修订或空结果
    C->>U: 退出，关闭查询事务
```

尚无对应 HTTP 入口；不把仓储 None 自动解释成公开 API 的 404。
