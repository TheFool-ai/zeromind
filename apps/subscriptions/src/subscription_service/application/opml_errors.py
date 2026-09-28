"""文件级错误与中断进度；逐条业务错误由导入报告表达。"""

from subscription_service.application.dto.opml_import import OpmlImportResult


class InvalidOpmlError(ValueError):
    """格式、结构、安全限制不满足，整个文件不应写入。"""


class OpmlTooLargeError(InvalidOpmlError):
    """上传或直接调用时内容超过字节上限。"""


class OpmlImportInterruptedError(RuntimeError):
    """非业务错误中断导入；此前已提交项不会被整批回滚。"""

    def __init__(self, result: OpmlImportResult) -> None:
        super().__init__("导入中断，可根据已完成结果重试")
        self.result = result
