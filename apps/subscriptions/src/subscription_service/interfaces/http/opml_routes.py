"""OPML 独立入口：流式限额读取原始 XML，不依赖 multipart 或服务端文件路径。"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from subscription_service.application.dto.opml_import import MAX_OPML_BYTES
from subscription_service.application.opml_errors import (
    InvalidOpmlError,
    OpmlImportInterruptedError,
    OpmlTooLargeError,
)
from subscription_service.application.opml_import_service import OpmlImportService


class ImportItemResponse(BaseModel):
    """index 对应候选来源顺序，避免错误报告回显可能带凭据的原始属性。"""

    model_config = ConfigDict(from_attributes=True)
    index: int
    status: Literal["created", "skipped", "failed"]
    code: str
    subscription_id: UUID | None


class ImportResponse(BaseModel):
    """完成和中断使用相同摘要；remaining 为尚未尝试处理的数量。"""

    model_config = ConfigDict(from_attributes=True)
    total: int
    created: int
    skipped: int
    failed: int
    remaining: int
    items: list[ImportItemResponse]


def create_opml_router(service: OpmlImportService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/subscriptions", tags=["订阅导入"])

    @router.post(
        "/import/opml",
        response_model=ImportResponse,
        summary="导入 OPML，已有来源跳过",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    media: {"schema": {"type": "string", "format": "binary"}}
                    for media in ("application/xml", "text/xml", "text/x-opml")
                },
            }
        },
        responses={
            413: {"description": "文件超过 1 MiB"},
            415: {"description": "非 XML 媒体类型"},
            422: {"description": "文件格式、结构或安全限制不满足"},
            503: {"description": "导入中断，detail.result 包含已提交进度"},
        },
    )
    async def import_opml(request: Request):
        media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media not in {"application/xml", "text/xml", "text/x-opml"}:
            raise HTTPException(
                415,
                detail={
                    "code": "unsupported_media_type",
                    "message": "请以原始 XML 请求体上传 OPML",
                },
            )
        # 不信任 Content-Length：分块请求同样受限，超过上限即停止继续收集。
        content = bytearray()
        try:
            async for chunk in request.stream():
                if len(content) + len(chunk) > MAX_OPML_BYTES:
                    raise OpmlTooLargeError("OPML 文件不能超过 1 MiB")
                content.extend(chunk)
            result = await service.import_document(bytes(content))
        except OpmlTooLargeError as exc:
            raise HTTPException(
                413, detail={"code": "opml_too_large", "message": str(exc)}
            ) from exc
        except InvalidOpmlError as exc:
            raise HTTPException(422, detail={"code": "invalid_opml", "message": str(exc)}) from exc
        except OpmlImportInterruptedError as exc:
            progress = ImportResponse.model_validate(exc.result).model_dump(mode="json")
            raise HTTPException(
                503,
                detail={
                    "code": "opml_import_interrupted",
                    "message": "导入中断；已提交记录保留，可重试文件",
                    "result": progress,
                },
            ) from exc
        return ImportResponse.model_validate(result)

    return router
