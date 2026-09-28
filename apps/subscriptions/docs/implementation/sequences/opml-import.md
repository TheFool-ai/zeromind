# SUB-005 OPML 导入时序

状态：已实现。导入只创建来源，不访问外部 Feed 或文章表。

```mermaid
sequenceDiagram
    actor C as 客户端
    participant H as 导入 HTTP
    participant A as OpmlImportService
    participant P as SafeOpmlReader
    participant U as 逐项 UoW
    participant R as 来源仓储
    C->>H: POST 原始 XML
    H->>H: 校验媒体类型，流式限制 1 MiB
    H->>A: import_document(bytes)
    A->>P: 完整安全解析
    alt 文件非法或超限
        P-->>H: 文件级错误
        H-->>C: 422 或 413，无数据库写入
    else 文件合法
        P-->>A: 有序候选项
        loop 每个候选来源，基础设施故障时终止
            A->>A: 规范化地址；非法记 failed，文件内已处理记 skipped
            opt 合法且文件内未成功处理
                A->>U: 新工作单元
                A->>R: find_by_address
                alt 已存在
                    R-->>A: 来源
                    A->>A: skipped，不调用 save
                else 不存在
                    A->>A: 领域创建校验，非法记 failed
                    opt 领域校验通过
                        A->>R: add + flush
                        A->>U: commit，确认后记 created
                    end
                end
                A->>U: 退出，回滚未提交状态并关闭
            end
        end
        A-->>H: 摘要与逐项结果
        H-->>C: 200（可含逐项校验失败）
    end
```

## 异常分支

查重后发生唯一冲突：退出当前工作单元回滚，记 already_exists/skipped，继续下一条；不复用失败会话。
其他存储或非业务异常：当前工作单元退出，应用服务停止循环，HTTP 返回 503 而非上图的 200。
503 的 detail.result 包含此前确认提交项、当前未确认成功项及 remaining。此前提交不回滚，重传按地址跳过。
非法候选不进入文件内成功去重集合，因此后续相同地址的合法项可以创建。
已有来源跳过先于新名称/分类校验，保证导入不会修改或重新启用它。
