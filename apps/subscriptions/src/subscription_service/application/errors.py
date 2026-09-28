"""应用用例错误；由协议层决定对应 HTTP 状态。"""


class SubscriptionNotFoundError(LookupError):
    """来源不存在。"""


class InvalidSubscriptionError(ValueError):
    """用户输入不符合订阅领域规则。"""
