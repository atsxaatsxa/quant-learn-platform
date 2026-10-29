"""
引擎自定义异常。

- ValidationError：输入校验失败。按验收「一票否决」规则，校验失败必须
  阻止报告产出（绝不在带病状态下输出回测报告）。
- DataError：数据层不可用（获取失败 / 空数据）。
"""


class ValidationError(Exception):
    """输入参数校验失败。携带 field 便于前端定位。"""

    def __init__(self, message: str, field: str = None):
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self):
        if self.field:
            return f"[{self.field}] {self.message}"
        return self.message


class DataError(Exception):
    """数据获取/解析失败。"""

    def __init__(self, message: str, symbol: str = None):
        super().__init__(message)
        self.message = message
        self.symbol = symbol
