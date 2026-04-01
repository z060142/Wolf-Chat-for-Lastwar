"""
统一JSON解析工具
提供带错误处理、验证和默认值的JSON解析功能
"""
import json
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


def safe_json_loads(
    json_str: str,
    default: Any = None,
    expected_type: Optional[type] = None,
    raise_on_error: bool = False
) -> Any:
    """
    安全的JSON解析函数

    Args:
        json_str: 要解析的JSON字符串
        default: 解析失败时的默认返回值
        expected_type: 期望的返回类型（dict, list等）
        raise_on_error: 是否在错误时抛出异常

    Returns:
        解析后的对象，失败时返回default

    Raises:
        ValueError: 当raise_on_error=True且解析失败时
    """
    if not json_str or not isinstance(json_str, str):
        logger.warning(f"Invalid JSON input type: {type(json_str)}")
        if raise_on_error:
            raise ValueError(f"Expected string, got {type(json_str)}")
        return default

    try:
        result = json.loads(json_str)

        # 类型验证
        if expected_type and not isinstance(result, expected_type):
            logger.warning(
                f"JSON type mismatch: expected {expected_type.__name__}, "
                f"got {type(result).__name__}"
            )
            if raise_on_error:
                raise ValueError(
                    f"Expected {expected_type.__name__}, got {type(result).__name__}"
                )
            return default

        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        if raise_on_error:
            raise ValueError(f"Invalid JSON: {e}") from e
        return default
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON: {e}")
        if raise_on_error:
            raise
        return default


def safe_json_dumps(
    obj: Any,
    default: str = "{}",
    ensure_ascii: bool = False,
    indent: Optional[int] = None
) -> str:
    """
    安全的JSON序列化函数

    Args:
        obj: 要序列化的对象
        default: 序列化失败时的默认返回值
        ensure_ascii: 是否确保ASCII编码
        indent: 缩进空格数

    Returns:
        JSON字符串
    """
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent)
    except (TypeError, ValueError) as e:
        logger.error(f"JSON encode error: {e}")
        return default


def validate_json_schema(data: Dict, required_keys: list) -> bool:
    """
    验证JSON对象是否包含必需的键

    Args:
        data: 要验证的字典
        required_keys: 必需的键列表

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False

    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        logger.warning(f"Missing required keys: {missing_keys}")
        return False

    return True
