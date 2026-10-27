"""
集中配置加载器。

config.yaml 是「单一事实来源」：标的池、回测区间、成本参数、风控阈值
全部在此一处定义，代码内不散落硬编码（对应验收维度 7「可复现复用」）。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.util.yaml_min import load_yaml_file

_CONFIG_PATH = os.path.join(_ROOT, "config.yaml")


def load_config(path: str = None) -> dict:
    """加载并返回配置字典。"""
    path = path or _CONFIG_PATH
    return load_yaml_file(path)


# 进程内缓存，避免重复解析
_CFG = None


def get_config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG


def config_root() -> str:
    return _ROOT
