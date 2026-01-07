"""
Base platform interface for forum implementations
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from playwright.async_api import Page, BrowserContext


class BasePlatform(ABC):
    """Abstract base class for all forum platforms"""
    
    def __init__(self, browser_context: Optional[BrowserContext] = None, main_page: Optional[Page] = None):
        self.browser_context = browser_context
        self.main_page = main_page
        self.is_logged_in = False
        self.platform_name = self.get_platform_name()
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the platform name (e.g., 'reddit', 'twitter', 'instagram')"""
        pass
    
    @abstractmethod
    def get_base_url(self) -> str:
        """Return the base URL for the platform"""
        pass
    
    @abstractmethod
    async def ensure_browser(self) -> bool:
        """Ensure browser is initialized and ready"""
        pass
    
    @abstractmethod
    async def login(self) -> str:
        """Login to the platform account"""
        pass
    
    @abstractmethod
    async def search_posts(self, keywords: str, limit: int = 100) -> str:
        """Search for posts by keywords
        
        Args:
            keywords: Search keywords
            limit: Maximum number of results to return
            
        Returns:
            Formatted string with search results
        """
        pass
    
    @abstractmethod
    async def get_post_content(self, url: str) -> str:
        """Get post content by URL
        
        Args:
            url: Post URL
            
        Returns:
            Post content as string
        """
        pass
    
    @abstractmethod
    async def get_post_comments(self, url: str) -> List[Dict[str, Any]]:
        """Get post comments (returns structured data)
        
        Args:
            url: Post URL
            
        Returns:
            List of comment dictionaries with keys: Username, Content, Time
        """
        pass
    
    @abstractmethod
    async def post_comment(self, url: str, comment_text: str, comment_type: str = "lead_gen") -> str:
        """Post a comment on a post
        
        Args:
            url: Post URL
            comment_text: Comment text to post
            comment_type: Type of comment (lead_gen, like, consult, professional)
            
        Returns:
            Success message
        """
        pass
    
    @abstractmethod
    async def reply_to_comment(self, url: str, comment_content: str, reply_text: str) -> str:
        """Reply to a specific comment
        
        Args:
            url: Post URL
            comment_content: Content of the comment to reply to
            reply_text: Reply text
            
        Returns:
            Success message
        """
        pass
    
    def get_search_url(self, keywords: str) -> str:
        """Generate search URL for the platform (can be overridden)"""
        base_url = self.get_base_url()
        return f"{base_url}/search?q={keywords}"

