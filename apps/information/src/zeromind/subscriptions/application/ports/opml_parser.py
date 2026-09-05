from typing import Protocol

from zeromind.subscriptions.application.dto.opml_preview import OpmlPreview


class OpmlParser(Protocol):
    def preview(self, data: bytes) -> OpmlPreview: ...
