"""
Platform registry for managing and accessing different forum platforms
"""
from typing import Dict, List, Optional, Type
from .base_platform import BasePlatform
from .reddit_platform import RedditPlatform
from .twitter_platform import TwitterPlatform
from .instagram_platform import InstagramPlatform
from .quora_platform import QuoraPlatform
from .linkedin_platform import LinkedInPlatform
from .tiktok_platform import TikTokPlatform


class PlatformRegistry:
    """Registry for managing platform instances"""
    
    _platforms: Dict[str, Type[BasePlatform]] = {
        'reddit': RedditPlatform,
        'twitter': TwitterPlatform,
        'instagram': InstagramPlatform,
        'quora': QuoraPlatform,
        'linkedin': LinkedInPlatform,
        'tiktok': TikTokPlatform,
    }
    
    _instances: Dict[str, BasePlatform] = {}
    
    @classmethod
    def register_platform(cls, name: str, platform_class: Type[BasePlatform]):
        """Register a new platform class"""
        cls._platforms[name.lower()] = platform_class
    
    @classmethod
    def get_platform(cls, name: str, browser_context=None, main_page=None) -> Optional[BasePlatform]:
        """Get or create a platform instance"""
        name_lower = name.lower()
        
        if name_lower not in cls._platforms:
            raise ValueError(f"Platform '{name}' is not supported. Available platforms: {list(cls._platforms.keys())}")
        
        # Use singleton pattern - reuse instance if exists
        if name_lower not in cls._instances:
            platform_class = cls._platforms[name_lower]
            cls._instances[name_lower] = platform_class(browser_context=browser_context, main_page=main_page)
        else:
            # Update browser context and page if provided
            instance = cls._instances[name_lower]
            if browser_context:
                instance.browser_context = browser_context
            if main_page:
                instance.main_page = main_page
        
        return cls._instances[name_lower]
    
    @classmethod
    def get_available_platforms(cls) -> List[str]:
        """Get list of available platform names"""
        return list(cls._platforms.keys())
    
    @classmethod
    def clear_instances(cls):
        """Clear all platform instances (useful for testing)"""
        cls._instances.clear()

