"""
Reddit platform implementation
Wraps existing Reddit functionality from service_mcp.py
"""
from .base_platform import BasePlatform
from typing import List, Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
import sys
import os

# Import the existing Reddit functions from service_mcp
# We'll use a lazy import approach to avoid circular dependencies
_reddit_functions = None

def _get_reddit_functions():
    """Lazy import of Reddit functions from service_mcp"""
    global _reddit_functions
    if _reddit_functions is None:
        # Import service_mcp functions
        import service_mcp
        _reddit_functions = {
            'ensure_browser': getattr(service_mcp, 'ensure_browser', None),
            'login_impl': getattr(service_mcp, 'login_impl', None),
            'search_notes_impl': getattr(service_mcp, 'search_notes_impl', None),
            'get_note_content_impl': getattr(service_mcp, 'get_note_content_impl', None),
            'get_note_comments_impl': getattr(service_mcp, 'get_note_comments_impl', None),
            '_get_note_comments_structured': getattr(service_mcp, '_get_note_comments_structured', None),
            'post_smart_comment_impl': getattr(service_mcp, 'post_smart_comment_impl', None),
            'reply_to_comment_impl': getattr(service_mcp, 'reply_to_comment_impl', None),
            'main_page': getattr(service_mcp, 'main_page', None),
            'browser_context': getattr(service_mcp, 'browser_context', None),
        }
    return _reddit_functions


class RedditPlatform(BasePlatform):
    """Reddit platform implementation using existing service_mcp functions"""
    
    def get_platform_name(self) -> str:
        return "reddit"
    
    def get_base_url(self) -> str:
        return "https://www.reddit.com"
    
    async def ensure_browser(self) -> bool:
        """Ensure browser is initialized"""
        funcs = _get_reddit_functions()
        ensure_browser = funcs.get('ensure_browser')
        if ensure_browser:
            return await ensure_browser()
        return False
    
    async def login(self) -> str:
        """Login to Reddit"""
        funcs = _get_reddit_functions()
        login_impl = funcs.get('login_impl')
        if login_impl:
            return await login_impl()
        return "Reddit login function not available"
    
    async def search_posts(self, keywords: str, limit: int = 100) -> str:
        """Search for Reddit posts"""
        funcs = _get_reddit_functions()
        search_notes_impl = funcs.get('search_notes_impl')
        if search_notes_impl:
            return await search_notes_impl(keywords, limit)
        return f"Reddit search not available for '{keywords}'"
    
    async def get_post_content(self, url: str) -> str:
        """Get Reddit post content"""
        funcs = _get_reddit_functions()
        get_note_content_impl = funcs.get('get_note_content_impl')
        if get_note_content_impl:
            return await get_note_content_impl(url)
        return f"Reddit post content extraction not available for {url}"
    
    async def get_post_comments(self, url: str) -> List[Dict[str, Any]]:
        """Get Reddit post comments"""
        funcs = _get_reddit_functions()
        get_comments = funcs.get('_get_note_comments_structured') or funcs.get('get_note_comments_impl')
        if get_comments:
            result = await get_comments(url)
            # If it returns a list, return it directly
            if isinstance(result, list):
                return result
            # Otherwise, try to parse string format
            return []
        return []
    
    async def post_comment(self, url: str, comment_text: str, comment_type: str = "lead_gen") -> str:
        """Post a comment on Reddit post"""
        funcs = _get_reddit_functions()
        post_smart_comment_impl = funcs.get('post_smart_comment_impl')
        if post_smart_comment_impl:
            return await post_smart_comment_impl(url, comment_type, comment_text)
        return f"Reddit comment posting not available"
    
    async def reply_to_comment(self, url: str, comment_content: str, reply_text: str) -> str:
        """Reply to a specific Reddit comment"""
        funcs = _get_reddit_functions()
        reply_to_comment_impl = funcs.get('reply_to_comment_impl')
        if reply_to_comment_impl:
            return await reply_to_comment_impl(url, comment_content, reply_text)
        return f"Reddit comment reply not available"
    
    def get_search_url(self, keywords: str) -> str:
        return f"{self.get_base_url()}/search/?q={keywords}"

