"""应用层可识别的业务与持久化冲突，不暴露 SQLAlchemy 类型。"""


class DuplicateSubscriptionError(ValueError):
    """规范化来源地址已经存在。"""


class DuplicateItemError(ValueError):
    """同一来源内的条目身份已经存在。"""


class ConcurrentModificationError(RuntimeError):
    """聚合在读取后被其他事务修改，调用方应重新加载并重新执行业务操作。"""
