"""
策略基类与参数 Schema 约定。

每个策略暴露：
  - key / name / description：标识与简介
  - course_ref：对应《365天量化金融》课程章节话术（教学层使用）
  - param_schema()：参数定义，供前端「参数化模板」界面自动渲染
  - validate_params(params)：参数校验（失败抛 ValidationError，阻止运行）
  - initialize(ctx) -> dict[symbol->weight] | None
  - decide(date, ctx) -> dict[symbol->weight] | None

权重约定：返回 {标的: 权重}，权重为「占组合总市值比例」，
总和可 <=1（<1 部分留现金）。引擎据此在下一交易日开盘调仓。
"""
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.engine.exceptions import ValidationError


class BaseStrategy:
    key = "base"
    name = "基础策略"
    description = ""
    course_ref = ""

    def initialize(self, ctx):
        return None

    def decide(self, date, ctx):
        return None

    def validate_params(self, params: dict):
        pass

    def param_schema(self) -> list:
        return []
