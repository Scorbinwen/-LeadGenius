"""
Platform abstraction layer for multi-forum support
"""
from .base_platform import BasePlatform
from .reddit_platform import RedditPlatform
from .platform_registry import PlatformRegistry

__all__ = ['BasePlatform', 'RedditPlatform', 'PlatformRegistry']

