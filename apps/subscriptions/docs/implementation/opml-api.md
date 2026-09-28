# OPML 导入接口

状态：已实现。POST `/api/v1/subscriptions/import/opml`，请求体为 XML 文件原始字节，不是文件路径、JSON 或 multipart。
支持 application/xml、text/xml、text/x-opml，可带 charset 参数；编码实际由 XML 声明决定。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/subscriptions/import/opml \
  -H 'Content-Type: application/xml' \
  --data-binary @subscriptions.opml
```

## 成功或逐项业务失败

完成处理返回 200；failed 大于零不改变 HTTP 状态，调用方应检查摘要及逐项结果。

```json
{
  "total": 2,
  "created": 1,
  "skipped": 1,
  "failed": 0,
  "remaining": 0,
  "items": [
    {"index": 1, "status": "created", "code": "created", "subscription_id": "00000000-0000-4000-8000-000000000001"},
    {"index": 2, "status": "skipped", "code": "duplicate_in_file", "subscription_id": null}
  ]
}
```

示例 UUID 仅用于说明。index 是候选 Feed 的 1 起始顺序，不包括文件夹或其他非 Feed 节点。
total = created + skipped + failed + remaining。items 按输入候选顺序排列，只含已处理项。
created 和直接查到的 already_exists 带来源 ID；文件内重复或并发唯一冲突的 skipped 允许 ID 为 null。

| status | code | 含义 |
| --- | --- | --- |
| created | created | 已确认提交 |
| skipped | already_exists | 已有来源或并发插入产生唯一冲突，不修改原记录 |
| skipped | duplicate_in_file | 同文件此前已成功处理该地址 |
| failed | invalid_address | 缺失或非法来源地址 |
| failed | invalid_subscription | 名称或分类等领域校验失败 |
| failed | storage_error | 未能确认该条处理成功，后续停止 |

## 文件级错误与中断

| HTTP | detail.code | 数据效果 |
| --- | --- | --- |
| 413 | opml_too_large | 超过 1 MiB，不开始写入 |
| 415 | unsupported_media_type | 不支持的 Content-Type，不开始写入 |
| 422 | invalid_opml | 格式、结构、安全或复杂度限制失败，不开始写入 |
| 503 | opml_import_interrupted | 保留此前已确认提交项；detail.result 包含上述摘要结构 |

上传中断或客户端断连不承诺收到报告；重传文件仍按地址跳过已提交来源。
当前无鉴权，不能直接暴露公网。安全上限和字段映射见 [功能说明](../features/opml-import.md)。
