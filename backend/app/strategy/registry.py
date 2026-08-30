"""策略注册表 - 管理所有可用策略"""

from app.strategy.base import Strategy
from app.log_config import get_logger

logger = get_logger(__name__)

_registry: dict[str, Strategy] = {}


def register(strategy: Strategy):
    """注册一个策略"""
    _registry[strategy.name] = strategy
    logger.info("策略已注册: %s", strategy.name)


def get(name: str) -> Strategy | None:
    """按名称获取策略"""
    return _registry.get(name)


def list_all() -> list[dict]:
    """列出所有已注册策略的信息"""
    return [s.to_dict() for s in _registry.values()]


def get_names() -> list[str]:
    """获取所有已注册策略名称"""
    return list(_registry.keys())


def auto_register():
    """自动注册所有内置策略（当前仅保留组合策略）"""
    from app.strategy.ma_combo import MAComboStrategy

    register(MAComboStrategy())
