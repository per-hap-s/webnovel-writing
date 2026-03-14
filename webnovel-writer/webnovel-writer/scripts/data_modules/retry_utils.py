#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retry_utils.py - 重试机制辅助模块

提供数据同步操作的重试能力：
- 可配置的重试次数和间隔
- 指数退避策略
- 同步失败标记机制
- 详细的日志记录
"""

import functools
import logging
import time
from typing import Callable, Type, Tuple, Any, Optional, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


class SyncStatus:
    """同步状态标记类，用于追踪同步失败的数据"""
    
    def __init__(self):
        self._pending_sync: dict = {}
        self._failed_count: dict = {}
        self._last_error: dict = {}
    
    def mark_pending(self, key: str, data: Any) -> None:
        """
        标记数据为待同步状态
        
        参数:
        - key: 数据标识键
        - data: 待同步的数据
        """
        self._pending_sync[key] = data
        logger.debug(f"[SyncStatus] 标记待同步: {key}")
    
    def mark_success(self, key: str) -> None:
        """
        标记同步成功，清除待同步状态
        
        参数:
        - key: 数据标识键
        """
        self._pending_sync.pop(key, None)
        self._failed_count.pop(key, None)
        self._last_error.pop(key, None)
        logger.debug(f"[SyncStatus] 同步成功: {key}")
    
    def mark_failed(self, key: str, error: Exception) -> None:
        """
        标记同步失败，记录错误信息
        
        参数:
        - key: 数据标识键
        - error: 异常对象
        """
        self._failed_count[key] = self._failed_count.get(key, 0) + 1
        self._last_error[key] = {
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": time.time()
        }
        logger.warning(f"[SyncStatus] 同步失败: {key}, 失败次数: {self._failed_count[key]}")
    
    def get_pending(self, key: str) -> Optional[Any]:
        """
        获取待同步的数据
        
        参数:
        - key: 数据标识键
        
        返回: 待同步的数据，不存在则返回 None
        """
        return self._pending_sync.get(key)
    
    def get_all_pending(self) -> dict:
        """获取所有待同步的数据"""
        return dict(self._pending_sync)
    
    def get_failed_count(self, key: str) -> int:
        """获取指定键的失败次数"""
        return self._failed_count.get(key, 0)
    
    def get_last_error(self, key: str) -> Optional[dict]:
        """获取指定键的最后错误信息"""
        return self._last_error.get(key)
    
    def clear_all(self) -> None:
        """清除所有待同步状态"""
        self._pending_sync.clear()
        self._failed_count.clear()
        self._last_error.clear()
        logger.debug("[SyncStatus] 已清除所有待同步状态")


def retry_sync(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    exponential_backoff: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    同步操作重试装饰器
    
    参数:
    - max_retries: 最大重试次数，默认 3 次
    - base_delay: 基础延迟时间（秒），默认 0.5 秒
    - max_delay: 最大延迟时间（秒），默认 5 秒
    - exponential_backoff: 是否使用指数退避，默认 True
    - exceptions: 需要重试的异常类型元组，默认所有异常
    - on_retry: 重试时的回调函数，参数为 (重试次数, 异常对象)
    - on_failure: 最终失败时的回调函数，参数为异常对象
    
    返回: 装饰后的函数
    
    示例:
    ```python
    @retry_sync(max_retries=3, base_delay=1.0)
    def sync_to_database(data):
        # 同步逻辑
        pass
    ```
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            f"[Retry] {func.__name__} 在第 {attempt + 1} 次尝试成功"
                        )
                    return result
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        delay = _calculate_delay(
                            attempt, base_delay, max_delay, exponential_backoff
                        )
                        
                        logger.warning(
                            f"[Retry] {func.__name__} 第 {attempt + 1} 次失败: {e}, "
                            f"{delay:.2f}秒后重试..."
                        )
                        
                        if on_retry:
                            try:
                                on_retry(attempt + 1, e)
                            except Exception as callback_err:
                                logger.error(f"[Retry] on_retry 回调执行失败: {callback_err}")
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} 达到最大重试次数 {max_retries}, "
                            f"最后错误: {e}"
                        )
                        
                        if on_failure:
                            try:
                                on_failure(e)
                            except Exception as callback_err:
                                logger.error(f"[Retry] on_failure 回调执行失败: {callback_err}")
            
            raise last_exception if last_exception else RuntimeError("未知重试错误")
        
        return wrapper
    return decorator


def retry_sync_call(
    func: Callable[P, T],
    *args: P.args,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    exponential_backoff: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs: P.kwargs
) -> T:
    """
    同步重试函数调用（非装饰器方式）
    
    参数:
    - func: 要执行的函数
    - *args: 函数位置参数
    - max_retries: 最大重试次数
    - base_delay: 基础延迟时间（秒）
    - max_delay: 最大延迟时间（秒）
    - exponential_backoff: 是否使用指数退避
    - exceptions: 需要重试的异常类型元组
    - **kwargs: 函数关键字参数
    
    返回: 函数执行结果
    
    示例:
    ```python
    result = retry_sync_call(
        sync_to_database,
        data,
        max_retries=3,
        base_delay=1.0
    )
    ```
    """
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
            if attempt > 0:
                logger.info(
                    f"[Retry] {func.__name__} 在第 {attempt + 1} 次尝试成功"
                )
            return result
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                delay = _calculate_delay(
                    attempt, base_delay, max_delay, exponential_backoff
                )
                
                logger.warning(
                    f"[Retry] {func.__name__} 第 {attempt + 1} 次失败: {e}, "
                    f"{delay:.2f}秒后重试..."
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"[Retry] {func.__name__} 达到最大重试次数 {max_retries}, "
                    f"最后错误: {e}"
                )
    
    raise last_exception if last_exception else RuntimeError("未知重试错误")


def retry_sync_safe(
    func: Callable[P, T],
    *args: P.args,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    exponential_backoff: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    default: Optional[T] = None,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_failure: Optional[Callable[[Exception], None]] = None,
    **kwargs: P.kwargs
) -> Tuple[bool, Optional[T], Optional[Exception]]:
    """
    安全重试函数调用，不抛出异常（v5.6 增强：添加回调支持）
    
    参数:
    - func: 要执行的函数
    - *args: 函数位置参数
    - max_retries: 最大重试次数
    - base_delay: 基础延迟时间（秒）
    - max_delay: 最大延迟时间（秒）
    - exponential_backoff: 是否使用指数退避
    - exceptions: 需要重试的异常类型元组
    - default: 失败时的默认返回值
    - on_retry: 重试时的回调函数，参数为 (重试次数, 异常对象)
    - on_failure: 最终失败时的回调函数，参数为异常对象
    - **kwargs: 函数关键字参数
    
    返回: (是否成功, 结果/默认值, 异常对象/None)
    
    示例:
    ```python
    success, result, error = retry_sync_safe(
        sync_to_database,
        data,
        max_retries=3,
        default=None,
        on_retry=lambda attempt, exc: print(f"重试 {attempt}: {exc}"),
        on_failure=lambda exc: print(f"最终失败: {exc}")
    )
    if not success:
        logger.error(f"同步失败: {error}")
    ```
    """
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
            if attempt > 0:
                logger.info(
                    f"[Retry] {func.__name__} 在第 {attempt + 1} 次尝试成功"
                )
            return True, result, None
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                delay = _calculate_delay(
                    attempt, base_delay, max_delay, exponential_backoff
                )
                
                logger.warning(
                    f"[Retry] {func.__name__} 第 {attempt + 1} 次失败: {e}, "
                    f"{delay:.2f}秒后重试..."
                )
                
                if on_retry:
                    try:
                        on_retry(attempt + 1, e)
                    except Exception as callback_err:
                        logger.error(f"[Retry] on_retry 回调执行失败: {callback_err}")
                
                time.sleep(delay)
            else:
                logger.error(
                    f"[Retry] {func.__name__} 达到最大重试次数 {max_retries}, "
                    f"最后错误: {e}"
                )
                
                if on_failure:
                    try:
                        on_failure(e)
                    except Exception as callback_err:
                        logger.error(f"[Retry] on_failure 回调执行失败: {callback_err}")
    
    return False, default, last_exception


def _calculate_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    exponential_backoff: bool
) -> float:
    """
    计算重试延迟时间
    
    参数:
    - attempt: 当前尝试次数（从 0 开始）
    - base_delay: 基础延迟时间
    - max_delay: 最大延迟时间
    - exponential_backoff: 是否使用指数退避
    
    返回: 延迟时间（秒）
    """
    if exponential_backoff:
        delay = base_delay * (2 ** attempt)
        return min(delay, max_delay)
    return base_delay


class RetryContext:
    """
    重试上下文管理器，用于需要重试的代码块
    
    示例:
    ```python
    with RetryContext(max_retries=3) as ctx:
        if ctx.should_retry:
            # 执行可能失败的操作
            pass
    ```
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 5.0,
        exponential_backoff: bool = True,
        exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.exceptions = exceptions
        self.attempt = 0
        self.last_exception: Optional[Exception] = None
    
    @property
    def should_retry(self) -> bool:
        """是否应该继续重试"""
        return self.attempt <= self.max_retries
    
    @property
    def remaining_retries(self) -> int:
        """剩余重试次数"""
        return max(0, self.max_retries - self.attempt)
    
    def __enter__(self) -> 'RetryContext':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            return False
        
        if not issubclass(exc_type, self.exceptions):
            return False
        
        self.last_exception = exc_val
        self.attempt += 1
        
        if self.attempt <= self.max_retries:
            delay = _calculate_delay(
                self.attempt - 1,
                self.base_delay,
                self.max_delay,
                self.exponential_backoff
            )
            logger.warning(
                f"[RetryContext] 第 {self.attempt} 次失败: {exc_val}, "
                f"{delay:.2f}秒后重试..."
            )
            time.sleep(delay)
            return True
        
        logger.error(
            f"[RetryContext] 达到最大重试次数 {self.max_retries}"
        )
        return False
