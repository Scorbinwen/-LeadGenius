from typing import Any, List, Dict, Optional, Tuple
import sys
import platform
import asyncio
import json
import os
import pandas as pd
from datetime import datetime
import time
from playwright.async_api import async_playwright
from fastmcp import FastMCP
from dotenv import load_dotenv

# Fix for Windows asyncio event loop policy
# Windows default ProactorEventLoop doesn't support subprocess operations properly
if platform.system() == "Windows":
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        # For Python < 3.8, use SelectorEventLoop
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("reddit_scraper")

# Global variables
BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# Ensure directories exist
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Store browser context to share between different methods
browser_context = None
main_page = None
is_logged_in = False
playwright_instance = None
current_loop_id = None  # Store event loop ID

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "openai", "gemini", "anthropic" or "ollama"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://10.10.10.217:11434/v1")  # Ollama server address (needs /v1 path)
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen2")  # Default to gpt-4o-mini, more economical

async def _call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> str:
    """Call LLM API
    
    Args:
        prompt: User prompt
        system_prompt: System prompt
        max_tokens: Maximum number of tokens
    
    Returns:
        Text returned by LLM
    """
    try:
        if LLM_PROVIDER == "gemini":
            # Import google genai (install with: pip install google-genai)
            try:
                from google import genai
            except ImportError:
                raise ImportError("google-genai package not installed. Install with: pip install google-genai")
            
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY environment variable not set")
            
            # Set GEMINI_API_KEY in environment if not already set
            if not os.getenv("GEMINI_API_KEY"):
                os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
            
            # The client gets the API key from the environment variable `GEMINI_API_KEY`
            client = genai.Client()
            
            # Set model name (default to gemini-2.5-flash if not specified)
            # Common models: gemini-2.5-flash, gemini-1.5-pro, gemini-1.5-flash
            model_name = LLM_MODEL if LLM_MODEL and "gemini" in LLM_MODEL.lower() else "gemini-2.5-flash"
            
            # Combine system prompt and user prompt
            # Gemini doesn't have a separate system parameter, so we combine them
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            else:
                full_prompt = prompt
            
            # Generate content
            # Note: Gemini API is synchronous, so we run it in executor to make it async-compatible
            response = client.models.generate_content(
                model=model_name, contents=full_prompt
            )
            
            return response.text
        
        elif LLM_PROVIDER == "anthropic":
            from anthropic import AsyncAnthropic
            
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
            client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            
            # Anthropic uses system parameter instead of adding system role in messages
            model_name = LLM_MODEL if "claude" in LLM_MODEL.lower() else "claude-3-5-sonnet-20241022"
            
            if system_prompt:
                response = await client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}]
                )
            else:
                response = await client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
            
            return response.content[0].text
        
        elif LLM_PROVIDER == "ollama":
            # Use Ollama server
            from openai import AsyncOpenAI
            
            # Ollama uses OpenAI-compatible API but doesn't need API Key
            # Set base_url to point to Ollama server
            client = AsyncOpenAI(
                base_url=OLLAMA_BASE_URL,
                api_key="ollama"  # Ollama doesn't need real API Key but requires a value
            )
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # Ollama model name, use default if not set
            model_name = LLM_MODEL if LLM_MODEL else "llama2"
            
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            return response.choices[0].message.content
        
        else:  # Default to OpenAI
            from openai import AsyncOpenAI
            
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            return response.choices[0].message.content
    
    except Exception as e:
        print(f"LLM call error: {str(e)}")
        # If LLM call fails, return empty string for caller to handle
        return ""

async def ensure_browser():
    """Ensure browser is started and logged in"""
    global browser_context, main_page, is_logged_in, playwright_instance, current_loop_id
    
    # Get current event loop ID
    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop_id = id(loop)
    
    # If browser context doesn't exist or event loop changed, recreate it
    if browser_context is None or current_loop_id != loop_id:
        # If old browser context exists and event loop changed, mark as invalid but don't close
        # Note: For persistent context, we shouldn't close it as it may be used by other processes
        # We just set reference to None, let new calls create new context
        if browser_context is not None and current_loop_id is not None and current_loop_id != loop_id:
            # Don't close persistent context, just clear reference
            # Persistent context will be automatically managed when no references exist
            browser_context = None
            main_page = None
            is_logged_in = False
        
        # Note: Don't stop playwright_instance because:
        # 1. Persistent context needs playwright_instance to manage browser process
        # 2. Stopping playwright_instance will close all related browser processes
        # 3. We just need to create new playwright_instance, old one will be garbage collected
        # If playwright_instance exists but event loop changed, create new instance
        if playwright_instance is not None and current_loop_id is not None and current_loop_id != loop_id:
            # Don't stop old instance, let it continue managing browser process
            # Create new instance for new connection
            playwright_instance = None
            browser_context = None
            main_page = None
            is_logged_in = False
        
        
        # Start browser
        playwright_instance = await async_playwright().start()
        
        # Use persistent context to save user state
        # Note: Persistent context will reuse same browser process even if previous context was "closed"
        # If previous browser is still running, launch_persistent_context will connect to existing browser
        try:
            browser_context = await playwright_instance.chromium.launch_persistent_context(
                user_data_dir=BROWSER_DATA_DIR,
                headless=False,  # Non-headless mode for user login convenience
                viewport={"width": 1280, "height": 800},
                timeout=60000
            )
        except Exception as e:
            error_msg = str(e)
            # If error is because browser was already closed, wait and retry
            if "closed" in error_msg.lower() or "Target page" in error_msg or "not found" in error_msg.lower():
                await asyncio.sleep(3)  # Wait for browser process to fully close
                try:
                    browser_context = await playwright_instance.chromium.launch_persistent_context(
                        user_data_dir=BROWSER_DATA_DIR,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                        timeout=60000
                    )
                except Exception as e2:
                    raise Exception(f"Unable to start browser. If problem persists, close all browser windows and retry. Error: {str(e2)}")
            else:
                raise
        
        # Record current event loop ID
        current_loop_id = loop_id
        
        # Create a new page
        if browser_context.pages:
            main_page = browser_context.pages[0]
            if main_page is None:
                main_page = await browser_context.new_page()
        else:
            main_page = await browser_context.new_page()
        
        # Set page-level timeout
        main_page.set_default_timeout(60000)
    
    # Check login status
    # FIXME: Cannot detect when user manually logs out, needs optimization
    if not is_logged_in:
        # Visit Reddit homepage
        await main_page.goto("https://www.reddit.com", timeout=60000)
        await asyncio.sleep(3)
        
        # Check if already logged in
        login_elements = await main_page.query_selector_all('text="Log In"')
        if login_elements:
            return False  # Need to login
        else:
            is_logged_in = True
            return True  # Already logged in
    
    return True

# Define original function (for direct calls from app.py)
async def login_impl() -> str:
    """Login to Reddit account"""
    global is_logged_in, main_page
    
    await ensure_browser()
    
    if is_logged_in:
        return "Already logged in to Reddit account"
    
    # Visit Reddit login page
    await main_page.goto("https://www.reddit.com", timeout=60000)
    await asyncio.sleep(3)
    
    # Find and click login button
    login_elements = await main_page.query_selector_all('text="Log In"')
    if login_elements:
        await login_elements[0].click()
        
        # Prompt user to manually login
        message = "Please complete the login in the opened browser window. The system will continue automatically after successful login."
        
        # Wait for user to login successfully
        max_wait_time = 180  # Wait 3 minutes
        wait_interval = 5
        waited_time = 0
        
        while waited_time < max_wait_time:
            # Check if login was successful
            still_login = await main_page.query_selector_all('text="Log In"')
            if not still_login:
                is_logged_in = True
                await asyncio.sleep(2)  # Wait for page to load
                return "Login successful!"
            
            # Continue waiting
            await asyncio.sleep(wait_interval)
            waited_time += wait_interval
        
        return "Login wait timeout. Please retry or login manually before using other features."
    else:
        is_logged_in = True
        return "Already logged in to Reddit account"

# MCP tool function (for MCP client use)
@mcp.tool()
async def login() -> str:
    """Login to Reddit account"""
    return await login_impl()

# Original function implementation (for use by app.py)
async def search_notes_impl(keywords: str, limit: int = 100) -> str:
    """Search posts by keywords
    
    Args:
        keywords: Search keywords
        limit: Maximum number of results to return
    """
    global main_page
    
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first"
    
    # Ensure main_page is valid
    if main_page is None:
        return "Browser page not initialized, please retry"
    
    # Build search URL and visit
    search_url = f"https://www.reddit.com/search/?q={keywords}"
    try:
        search_start_time = time.time()
        print(f"[TIMING] Starting search stage - Searching Reddit for: {keywords}")
        print(f"Search URL: {search_url}")
        
        # Stage 1: Navigate to search page
        nav_start = time.time()
        await main_page.goto(search_url, timeout=60000, wait_until="networkidle")
        nav_time = time.time() - nav_start
        print(f"[TIMING] Navigation to search page took: {nav_time:.2f}s")
        
        # Wait for search results to load - Reddit uses dynamic loading
        # Try to wait for at least one post element instead of fixed sleep
        wait_start = time.time()
        try:
            # Wait for post elements to appear (max 5 seconds)
            await main_page.wait_for_selector('a[href*="/r/"][href*="/comments/"], a[data-testid="post-title"]', timeout=5000)
            wait_time = time.time() - wait_start
            print(f"[TIMING] Waiting for search results to appear took: {wait_time:.2f}s")
        except:
            # Fallback: short wait if selector not found
            await asyncio.sleep(1)
            wait_time = time.time() - wait_start
            print(f"[TIMING] Fallback wait took: {wait_time:.2f}s")
        
        # Check current URL to verify we're on the search page
        current_url = main_page.url
        print(f"Current page URL: {current_url}")
        
        # Stage 2: Find post elements
        find_start = time.time()
        # Try multiple selectors for Reddit search results
        # Reddit search results can have different structures depending on the view
        post_elements = []
        
        # Method 1: Look for post title links (most common)
        # Reddit post links contain /r/ and /comments/
        method1_start = time.time()
        try:
            # Wait for at least one post to appear
            await main_page.wait_for_selector('a[href*="/r/"][href*="/comments/"]', timeout=10000)
            post_elements = await main_page.query_selector_all('a[href*="/r/"][href*="/comments/"]')
            method1_time = time.time() - method1_start
            print(f"[TIMING] Method 1 (post title links) took: {method1_time:.2f}s, found {len(post_elements)} elements")
        except Exception as e:
            method1_time = time.time() - method1_start
            print(f"[TIMING] Method 1 failed after {method1_time:.2f}s: {e}")
        
        # Method 2: If no results, try data-testid selector (new Reddit design)
        if len(post_elements) == 0:
            method2_start = time.time()
            try:
                await main_page.wait_for_selector('a[data-testid="post-title"]', timeout=5000)
                post_elements = await main_page.query_selector_all('a[data-testid="post-title"]')
                method2_time = time.time() - method2_start
                print(f"[TIMING] Method 2 (data-testid) took: {method2_time:.2f}s, found {len(post_elements)} elements")
            except Exception as e:
                method2_time = time.time() - method2_start
                print(f"[TIMING] Method 2 failed after {method2_time:.2f}s: {e}")
        
        # Method 3: Try looking for any link with /r/ and /comments/ pattern
        if len(post_elements) == 0:
            method3_start = time.time()
            try:
                all_links = await main_page.query_selector_all('a[href*="/r/"]')
                print(f"Found {len(all_links)} links with /r/ pattern")
                for link in all_links:
                    href = await link.get_attribute('href')
                    if href and '/comments/' in href and '/r/' in href:
                        post_elements.append(link)
                method3_time = time.time() - method3_start
                print(f"[TIMING] Method 3 (pattern matching) took: {method3_time:.2f}s, found {len(post_elements)} elements")
            except Exception as e:
                method3_time = time.time() - method3_start
                print(f"[TIMING] Method 3 failed after {method3_time:.2f}s: {e}")
        
        find_time = time.time() - find_start
        print(f"[TIMING] Total time to find post elements: {find_time:.2f}s")
        print(f"Found {len(post_elements)} post elements after all methods")
        
        search_total_time = time.time() - search_start_time
        print(f"[TIMING] Total search stage time: {search_total_time:.2f}s")
        
        post_links = []
        post_titles = []
        
        for element in post_elements:
            try:
                href = await element.get_attribute('href')
                if href and '/r/' in href and '/comments/' in href:
                    # Skip if it's already in our list
                    if any(href in link for link in post_links):
                        continue
                    
                    # Build full URL
                    if href.startswith('/'):
                        full_url = f"https://www.reddit.com{href}"
                    elif href.startswith('http'):
                        full_url = href
                    else:
                        full_url = f"https://www.reddit.com/{href}"
                    
                    # Clean up URL (remove query parameters and fragments)
                    if '?' in full_url:
                        full_url = full_url.split('?')[0]
                    if '#' in full_url:
                        full_url = full_url.split('#')[0]
                    
                    post_links.append(full_url)
                    
                    # Try to get post title
                    try:
                        # Try different methods to get title
                        title = await element.text_content()
                        if not title or title.strip() == "":
                            # Try getting title from parent or sibling elements
                            title_element = await element.query_selector('h3, h2, .title, [data-testid="post-title"]')
                            if title_element:
                                title = await title_element.text_content()
                            else:
                                title = "Unknown title"
                    except:
                        title = "Unknown title"
                    
                    if title:
                        title = title.strip()
                    else:
                        title = "Unknown title"
                    
                    post_titles.append(title)
            except Exception as e:
                # Skip this element if there's an error
                continue
        
        # Remove duplicates
        unique_posts = []
        seen_urls = set()
        for url, title in zip(post_links, post_titles):
            if url not in seen_urls:
                seen_urls.add(url)
                unique_posts.append({"url": url, "title": title})
        
        # Limit number of results
        unique_posts = unique_posts[:limit]
        
        # Format return results
        if unique_posts:
            result = "Search results:\n\n"
            for i, post in enumerate(unique_posts, 1):
                result += f"{i}. {post['title']}\n   Link: {post['url']}\n\n"
            
            return result
        else:
            return f"No posts found related to \"{keywords}\""
    
    except Exception as e:
        return f"Error searching posts: {str(e)}"

# MCP tool function
@mcp.tool()
async def search_notes(keywords: str, limit: int = 100) -> str:
    """Search posts by keywords"""
    return await search_notes_impl(keywords, limit)

# Original function implementation (for use by app.py)
async def get_note_content_impl(url: str) -> str:
    """Get post content
    
    Args:
        url: Post URL
    """
    global main_page
    
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first"
    
    # Ensure main_page is valid
    if main_page is None:
        return "Browser page not initialized, please retry"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Wait for post content to appear instead of fixed sleep
        try:
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
        except:
            await asyncio.sleep(1)  # Minimal fallback
        
        # Get post content
        post_content = {}
        
        # Get post title
        try:
            title_element = await main_page.query_selector('text="edited"')
            if title_element:
                title = await title_element.evaluate('(el) => el.previousElementSibling ? el.previousElementSibling.textContent : ""')
                post_content["Title"] = title.strip() if title else "Unknown title"
            else:
                post_content["Title"] = "Unknown title"
        except Exception as e:
            post_content["Title"] = "Unknown title"
        
        # Get author
        try:
            author_element = await main_page.query_selector('a[href*="/user/profile/"]')
            if author_element:
                author = await author_element.text_content()
                post_content["Author"] = author.strip() if author else "Unknown author"
            else:
                post_content["Author"] = "Unknown author"
        except Exception as e:
            post_content["Author"] = "Unknown author"
        
        # Get publish time
        try:
            time_selectors = [
                'text=/\\d{4}-\\d{2}-\\d{2}/',
                'text=/\\d+ months? ago/',
                'text=/\\d+ days? ago/',
                'text=/\\d+ hours? ago/',
                'text=/today/',
                'text=/yesterday/'
            ]
            
            post_content["PublishTime"] = "Unknown"
            for selector in time_selectors:
                time_element = await main_page.query_selector(selector)
                if time_element:
                    post_content["PublishTime"] = await time_element.text_content()
                    break
        except Exception as e:
            post_content["PublishTime"] = "Unknown"
        
        # Get post body content
        try:
            content_selectors = [
                'div.content', 
                'div.note-content',
                'article',
                'div.desc'
            ]
            
            post_content["Content"] = "Failed to get content"
            for selector in content_selectors:
                content_element = await main_page.query_selector(selector)
                if content_element:
                    content_text = await content_element.text_content()
                    if content_text and len(content_text.strip()) > 10:
                        post_content["Content"] = content_text.strip()
                        break
            
            # Use JavaScript to extract main text content
            if post_content["Content"] == "Failed to get content":
                content_text = await main_page.evaluate('''
                    () => {
                        const contentElements = Array.from(document.querySelectorAll('div, p, article'))
                            .filter(el => {
                                const text = el.textContent.trim();
                                return text.length > 50 && text.length < 5000 &&
                                    el.querySelectorAll('a, button').length < 5 &&
                                    el.children.length < 10;
                            })
                            .sort((a, b) => b.textContent.length - a.textContent.length);
                        
                        if (contentElements.length > 0) {
                            return contentElements[0].textContent.trim();
                        }
                        
                        return null;
                    }
                ''')
                
                if content_text:
                    post_content["Content"] = content_text
        except Exception as e:
            post_content["Content"] = f"Error getting content: {str(e)}"
        
        # Format return results
        result = f"Title: {post_content['Title']}\n"
        result += f"Author: {post_content['Author']}\n"
        result += f"Publish Time: {post_content['PublishTime']}\n"
        result += f"Link: {url}\n\n"
        result += f"Content:\n{post_content['Content']}"
        
        return result
    
    except Exception as e:
        return f"Error getting post content: {str(e)}"

@mcp.tool()
async def get_note_comments(url: str) -> str:
    """Get post comments
    
    Args:
        url: Post URL
    """
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Wait for post content to appear instead of fixed sleep
        try:
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
        except:
            await asyncio.sleep(1)  # Minimal fallback
        
        # Scroll to comment section first
        comment_section_locators = [
            main_page.get_by_text("comments", exact=False),
            main_page.get_by_text("comment", exact=False),
            main_page.locator("text=comment").first
        ]
        
        for locator in comment_section_locators:
            try:
                if await locator.count() > 0:
                    await locator.scroll_into_view_if_needed(timeout=5000)
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue
        
        # Scroll page to load more comments
        for i in range(8):
            try:
                await main_page.evaluate("window.scrollBy(0, 500)")
                # Reduced wait for scroll
                await asyncio.sleep(0.3)
                
                # Try to click "Load more comments" button
                more_comment_selectors = [
                    "text=Load more comments",
                    "text=View more comments",
                    "text=Load more",
                    "text=View all"
                ]
                
                for selector in more_comment_selectors:
                    try:
                        more_btn = main_page.locator(selector).first
                        if await more_btn.count() > 0 and await more_btn.is_visible():
                            await more_btn.click()
                            await asyncio.sleep(2)
                    except Exception:
                        continue
            except Exception:
                pass
        
        # Get comments
        comments = []
        
        # Use specific comment selectors
        comment_selectors = [
            "div.comment-item", 
            "div.commentItem",
            "div.comment-content",
            "div.comment-wrapper",
            "section.comment",
            "div.feed-comment"
        ]
        
        for selector in comment_selectors:
            comment_elements = main_page.locator(selector)
            count = await comment_elements.count()
            if count > 0:
                for i in range(count):
                    try:
                        comment_element = comment_elements.nth(i)
                        
                        # Extract commenter name
                        username = "Unknown user"
                        username_selectors = ["span.user-name", "a.name", "div.username", "span.nickname", "a.user-nickname"]
                        for username_selector in username_selectors:
                            username_el = comment_element.locator(username_selector).first
                            if await username_el.count() > 0:
                                username = await username_el.text_content()
                                username = username.strip()
                                break
                        
                        # If not found, try to find through user link
                        if username == "Unknown user":
                            user_link = comment_element.locator('a[href*="/user/profile/"]').first
                            if await user_link.count() > 0:
                                username = await user_link.text_content()
                                username = username.strip()
                        
                        # Extract comment content
                        content = "Unknown content"
                        content_selectors = ["div.content", "p.content", "div.text", "span.content", "div.comment-text"]
                        for content_selector in content_selectors:
                            content_el = comment_element.locator(content_selector).first
                            if await content_el.count() > 0:
                                content = await content_el.text_content()
                                content = content.strip()
                                break
                        
                        # If content not found, content might be in the comment element itself
                        if content == "Unknown content":
                            full_text = await comment_element.text_content()
                            if username != "Unknown user" and username in full_text:
                                content = full_text.replace(username, "").strip()
                            else:
                                content = full_text.strip()
                        
                        # Extract comment time
                        time_location = "Unknown time"
                        time_selectors = ["span.time", "div.time", "span.date", "div.date", "time"]
                        for time_selector in time_selectors:
                            time_el = comment_element.locator(time_selector).first
                            if await time_el.count() > 0:
                                time_location = await time_el.text_content()
                                time_location = time_location.strip()
                                break
                        
                        # If content has sufficient length and username found, add comment
                        if username != "Unknown user" and content != "Unknown content" and len(content) > 2:
                            comments.append({
                                "Username": username,
                                "Content": content,
                                "Time": time_location
                            })
                    except Exception:
                        continue
                
                # If comments found, don't continue trying other selectors
                if comments:
                    break
        
        # If no comments found, try other methods
        if not comments:
            # Get all username elements
            username_elements = main_page.locator('a[href*="/user/profile/"]')
            username_count = await username_elements.count()
            
            if username_count > 0:
                for i in range(username_count):
                    try:
                        username_element = username_elements.nth(i)
                        username = await username_element.text_content()
                        
                        # Try to get comment content
                        content = await main_page.evaluate('''
                            (usernameElement) => {
                                const parent = usernameElement.parentElement;
                                if (!parent) return null;
                                
                                // Try to get next sibling element
                                let sibling = usernameElement.nextElementSibling;
                                while (sibling) {
                                    const text = sibling.textContent.trim();
                                    if (text) return text;
                                    sibling = sibling.nextElementSibling;
                                }
                                
                                // Try to get parent element text and filter out username
                                const allText = parent.textContent.trim();
                                if (allText && allText.includes(usernameElement.textContent.trim())) {
                                    return allText.replace(usernameElement.textContent.trim(), '').trim();
                                }
                                
                                return null;
                            }
                        ''', username_element)
                        
                        if username and content:
                            comments.append({
                                "Username": username.strip(),
                                "Content": content.strip(),
                                "Time": "Unknown time"
                            })
                    except Exception:
                        continue
        
        # Format return results
        if comments:
            result = f"Found {len(comments)} comments:\n\n"
            for i, comment in enumerate(comments, 1):
                result += f"{i}. {comment['Username']} ({comment['Time']}): {comment['Content']}\n\n"
            return result
        else:
            return "No comments found. The post may have no comments or the comment section is inaccessible."
    
    except Exception as e:
        return f"Error getting comments: {str(e)}"

@mcp.tool()
async def post_smart_comment(url: str, comment_type: str = "lead_gen") -> str:
    """Post smart comment based on post content to increase exposure and guide users to follow or DM
    
    Args:
        url: Post URL
        comment_type: Comment type, options:
                     "lead_gen" - Guide users to follow or DM
                     "like" - Simple interaction to gain favor
                     "consult" - Increase interaction through questions
                     "professional" - Show professional knowledge to establish authority
    """
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first to post comments"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Wait for post content to appear instead of fixed sleep
        try:
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
        except:
            await asyncio.sleep(1)  # Minimal fallback
        
        # Get post content for analysis
        post_content = {}
        
        # Get post title
        try:
            title_element = await main_page.query_selector('text="edited"')
            if title_element:
                title = await title_element.evaluate('(el) => el.previousElementSibling ? el.previousElementSibling.textContent : ""')
                post_content["Title"] = title.strip() if title else "Unknown title"
            else:
                post_content["Title"] = "Unknown title"
        except Exception:
            post_content["Title"] = "Unknown title"
        
        # Get author
        try:
            author_element = await main_page.query_selector('a[href*="/user/profile/"]')
            if author_element:
                author = await author_element.text_content()
                post_content["Author"] = author.strip() if author else "Unknown author"
            else:
                post_content["Author"] = "Unknown author"
        except Exception:
            post_content["Author"] = "Unknown author"
        
        # Get post body content
        try:
            content_selectors = [
                'div.content', 
                'div.note-content',
                'article',
                'div.desc'
            ]
            
            post_content["Content"] = "Failed to get content"
            for selector in content_selectors:
                content_element = await main_page.query_selector(selector)
                if content_element:
                    content_text = await content_element.text_content()
                    if content_text and len(content_text.strip()) > 10:
                        post_content["Content"] = content_text.strip()
                        break
            
            # Use JavaScript to extract main text content
            if post_content["Content"] == "Failed to get content":
                content_text = await main_page.evaluate('''
                    () => {
                        const contentElements = Array.from(document.querySelectorAll('div, p, article'))
                            .filter(el => {
                                const text = el.textContent.trim();
                                return text.length > 50 && text.length < 5000 &&
                                    el.querySelectorAll('a, button').length < 5 &&
                                    el.children.length < 10;
                            })
                            .sort((a, b) => b.textContent.length - a.textContent.length);
                        
                        if (contentElements.length > 0) {
                            return contentElements[0].textContent.trim();
                        }
                        
                        return null;
                    }
                ''')
                
                if content_text:
                    post_content["Content"] = content_text
        except Exception:
            post_content["Content"] = "Failed to get content"
        
        # Generate smart comment based on post content and comment type
        comment_text = await _generate_smart_comment(post_content, comment_type)
        
        # Locate comment input box based on page snapshot
        # Locate comment area first
        try:
            # Try to find comment count area first, it usually contains "comments" text
            comment_count_selectors = [
                'text="comments"',
                'text="comment"',
                'text=/\\d+ comments/',
            ]
            
            for selector in comment_count_selectors:
                try:
                    comment_count_element = await main_page.query_selector(selector)
                    if comment_count_element:
                        await comment_count_element.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue
                
            # Locate comment input box
            input_box_selectors = [
                'paragraph:has-text("Add a comment...")',
                'text="Add a comment..."',
                'text="What are your thoughts?"',
                'div[contenteditable="true"]',
                'textarea[placeholder*="comment"]'
            ]
            
            comment_input = None
            for selector in input_box_selectors:
                try:
                    input_element = await main_page.query_selector(selector)
                    if input_element and await input_element.is_visible():
                        await input_element.scroll_into_view_if_needed()
                        await asyncio.sleep(1)
                        comment_input = input_element
                        break
                except Exception:
                    continue
                    
            # If all above methods failed, try using JavaScript to find
            if not comment_input:
                comment_input = await main_page.evaluate('''
                    () => {
                        // Find elements containing "Add a comment" or similar
                        const elements = Array.from(document.querySelectorAll('*'))
                            .filter(el => el.textContent && (
                                el.textContent.includes('Add a comment') ||
                                el.textContent.includes('What are your thoughts')
                            ));
                        if (elements.length > 0) return elements[0];
                        
                        // Find editable div elements
                        const editableDivs = Array.from(document.querySelectorAll('div[contenteditable="true"]'));
                        if (editableDivs.length > 0) return editableDivs[0];
                        
                        return null;
                    }
                ''')
                
                if comment_input:
                    comment_input = await main_page.query_selector_all('*')[-1]  # Use last element as placeholder
            
            if not comment_input:
                return "Unable to find comment input box, cannot post comment"
            
            # Click comment input box
            await comment_input.click()
            # Wait for input to be focused/ready instead of fixed sleep
            try:
                await comment_input.wait_for(state="visible", timeout=500)
            except:
                await asyncio.sleep(0.2)  # Minimal wait for focus
            
            # Type comment content using keyboard
            await main_page.keyboard.type(comment_text, delay=30)  # Reduced delay
            # Reduced wait after typing
            await asyncio.sleep(0.3)
            
            # Try to send using Enter key
            try:
                # Look for send button
                send_button_selectors = [
                    'button:has-text("Comment")',
                    'button:has-text("Post")',
                    'button[type="submit"]'
                ]
                
                send_button = None
                for selector in send_button_selectors:
                    elements = await main_page.query_selector_all(selector)
                    for element in elements:
                        text_content = await element.text_content()
                        if text_content and ('Comment' in text_content or 'Post' in text_content):
                            send_button = element
                            break
                    if send_button:
                        break
                
                if send_button:
                    await send_button.click()
                else:
                    # If send button not found, use Enter key
                    await main_page.keyboard.press('Enter')
                
                await asyncio.sleep(3)  # Wait for comment to be sent
                
                return f"Successfully posted comment: {comment_text}"
            except Exception as e:
                # If clicking send button failed, try sending via Enter key
                try:
                    await main_page.keyboard.press('Enter')
                    await asyncio.sleep(3)
                    return f"Comment sent via Enter key: {comment_text}"
                except Exception as press_error:
                    return f"Error trying to send comment: {str(e)}, Enter key also failed: {str(press_error)}"
                
        except Exception as e:
            return f"Error operating comment section: {str(e)}"
    
    except Exception as e:
        return f"Error posting comment: {str(e)}"

async def _analyze_comment_match(comment_content: str, product_description: str) -> Dict[str, Any]:
    """Use LLM to analyze comment content and determine if product is needed
    
    Args:
        comment_content: Comment content
        product_description: Product description
    
    Returns:
        Dictionary containing match score, whether product is needed, matched keywords, etc.
    """
    system_prompt = """You are a professional product promotion assistant. Your task is to analyze user comments and determine if the user needs a product.

Please carefully analyze the comment content, considering the following factors:
1. Whether the user expressed purchase intent (e.g., "want", "need", "looking for recommendations", etc.)
2. Whether the comment content is related to the product
3. Whether the user already owns the product (e.g., "already have", "already bought", etc.)
4. The tone and intent of the comment

Please return the analysis result in JSON format as follows:
{
    "match_score": 0-100 score indicating match level,
    "needs_product": true/false indicating if product is needed,
    "reason": "Brief explanation of the judgment"
}

Scoring criteria:
- 80-100 points: Strong need, clearly expressed purchase intent
- 60-79 points: Possible need, related demand expression
- 40-59 points: General need, slight relevance
- 0-39 points: No need or uncertain
"""
    
    user_prompt = f"""Product description: {product_description}

User comment: {comment_content}

Please analyze this comment and determine if the user needs this product. Only return JSON format result, no other text."""
    
    try:
        # Call LLM for analysis
        llm_response = await _call_llm(user_prompt, system_prompt, max_tokens=200)
        
        if not llm_response:
            # LLM call failed, use simple fallback logic
            return await _analyze_comment_match_fallback(comment_content, product_description)
        
        # Try to parse JSON response
        import re
        # Extract JSON part (LLM may have returned other text)
        json_match = re.search(r'\{[^{}]*\}', llm_response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            
            # Validate and normalize results
            match_score = float(result.get("match_score", 0))
            match_score = max(0, min(100, match_score))  # Ensure within 0-100 range
            
            needs_product = bool(result.get("needs_product", False))
            reason = result.get("reason", "")
            
            return {
                "match_score": match_score,
                "needs_product": needs_product,
                "reason": reason,
                "matched_keywords": [],  # LLM analysis doesn't need keywords
                "has_need_expression": needs_product
            }
        else:
            # JSON parsing failed, use fallback
            return await _analyze_comment_match_fallback(comment_content, product_description)
    
    except Exception as e:
        print(f"Error analyzing comment with LLM: {str(e)}")
        # On error, use fallback logic
        return await _analyze_comment_match_fallback(comment_content, product_description)

async def _analyze_comment_match_fallback(comment_content: str, product_description: str) -> Dict[str, Any]:
    """Fallback: Simple keyword matching analysis (used when LLM is unavailable)"""
    import re
    
    # Extract product keywords
    product_keywords = []
    product_words = re.findall(r'[\u4e00-\u9fa5]+|\w+', product_description.lower())
    product_keywords.extend(product_words)
    
    # Add common need expression words
    need_keywords = [
        "need", "want", "looking for", "recommend", "where", "how", "buy",
        "anyone", "who has", "recommendation", "link", "purchase",
        "where to buy", "price", "worth", "interested", "trying",
        "suitable", "good", "worth buying", "worth it"
    ]
    
    comment_lower = comment_content.lower()
    has_need_expression = any(keyword in comment_lower for keyword in need_keywords)
    
    matched_keywords = []
    for keyword in product_keywords:
        if len(keyword) > 1 and keyword in comment_lower:
            matched_keywords.append(keyword)
    
    match_score = 0.0
    if has_need_expression:
        match_score += 30.0
    match_score += len(matched_keywords) * 20.0
    if 10 <= len(comment_content) <= 200:
        match_score += 10.0
    
    exclude_keywords = ["don't need", "don't want", "not buying", "not interested", "already have", "already bought"]
    if any(keyword in comment_lower for keyword in exclude_keywords):
        match_score = 0.0
    
    match_score = min(100.0, match_score)
    needs_product = match_score >= 40.0
    
    return {
        "match_score": match_score,
        "needs_product": needs_product,
        "matched_keywords": matched_keywords,
        "has_need_expression": has_need_expression,
        "reason": "Using keyword matching analysis"
    }

async def _generate_reply_content(comment_content: str, product_description: str, username: str = "") -> str:
    """Use LLM to generate humanized reply content based on comment and product description
    
    Args:
        comment_content: Comment content
        product_description: Product description
        username: Commenter username
    
    Returns:
        Generated reply content
    """
    system_prompt = """You are a professional product promotion assistant. Your task is to generate a natural, friendly, and non-intrusive reply based on user comments and product information.

Requirements:
1. Reply should be natural and humanized, like a conversation between friends, not like a hard advertisement
2. Reply should address the user's specific needs, not be generic
3. Tone should be friendly and gentle, not overly promotional
4. You can appropriately address the user (if username is provided)
5. Naturally guide users to DM for more information, but not too directly
6. Keep reply length within 80 words
7. Don't use overly commercial terms like "discount", "promotion", "limited time", etc.
8. Should conform to Reddit platform community atmosphere, avoid violating content

Example styles:
- "Hi, I see you're looking for XX, I happen to have related products that might help you. Feel free to DM me if you're interested~"
- "Hey, I noticed your need. I have XX here that should meet your requirements. DM me if you need more info~"

Only return the reply content, no other explanatory text."""
    
    user_prompt = f"""Product description: {product_description}

User comment: {comment_content}
"""
    
    if username and username != "Unknown user":
        user_prompt += f"Username: {username}\n"
    
    user_prompt += "\nPlease generate a natural and friendly reply based on the above information."
    
    try:
        # Call LLM to generate reply
        reply = await _call_llm(user_prompt, system_prompt, max_tokens=150)
        
        if not reply:
            # LLM call failed, use fallback
            return await _generate_reply_content_fallback(comment_content, product_description, username)
        
        # Clean reply content (remove possible quotes, extra spaces, etc.)
        reply = reply.strip()
        # Remove possible quote wrapping
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        if reply.startswith("'") and reply.endswith("'"):
            reply = reply[1:-1]
        
        # Ensure appropriate length
        if len(reply) > 100:
            reply = reply[:97] + "..."
        
        # Ensure reply is not empty
        if not reply or len(reply) < 5:
            return await _generate_reply_content_fallback(comment_content, product_description, username)
        
        return reply
    
    except Exception as e:
        print(f"Error generating reply with LLM: {str(e)}")
        # On error, use fallback
        return await _generate_reply_content_fallback(comment_content, product_description, username)

async def _generate_search_keywords(product_description: str) -> str:
    """Use LLM to generate search keywords based on product description
    
    Args:
        product_description: Product description
    
    Returns:
        Generated search keywords (multiple keywords separated by space or comma)
    """
    system_prompt = """You are a professional search keyword generation assistant. Your task is to generate keywords suitable for searching on Reddit platform based on product description.

Requirements:
1. Extract core features and uses of the product
2. Generate 2-5 most relevant search keywords
3. Keywords should match Reddit users' search habits
4. Keywords should be concise and accu rate, avoid being too long
5. Multiple keywords separated by space, not comma
6. Prioritize popular terms users might search for

Examples:
- Product description: "High-quality cotton T-shirt, multiple colors available, comfortable and breathable, suitable for daily wear"
- Search keywords: "T-shirt cotton comfortable"

- Product description: "Natural organic face mask, hydrating and moisturizing, suitable for sensitive skin"
- Search keywords: "face mask hydrating sensitive skin"

Only return keywords, no other explanatory text."""
    
    user_prompt = f"""Product description: {product_description}

Please generate keywords suitable for searching on Reddit based on this product description. Only return keywords, separated by space."""
    
    try:
        # Call LLM to generate keywords
        keywords = await _call_llm(user_prompt, system_prompt, max_tokens=50)
        
        if not keywords:
            # LLM call failed, use fallback
            return await _generate_search_keywords_fallback(product_description)
        
        # Clean keywords (remove possible quotes, extra spaces, etc.)
        keywords = keywords.strip()
        # Remove possible quote wrapping
        if keywords.startswith('"') and keywords.endswith('"'):
            keywords = keywords[1:-1]
        if keywords.startswith("'") and keywords.endswith("'"):
            keywords = keywords[1:-1]
        
        # Handle possible comma separation, convert to space
        keywords = keywords.replace(",", " ").replace("，", " ")
        # Clean extra spaces
        keywords = " ".join(keywords.split())
        
        # Ensure keywords are not empty
        if not keywords or len(keywords) < 2:
            return await _generate_search_keywords_fallback(product_description)
        
        return keywords
    
    except Exception as e:
        print(f"Error generating search keywords with LLM: {str(e)}")
        # On error, use fallback
        return await _generate_search_keywords_fallback(product_description)

async def _generate_search_keywords_fallback(product_description: str) -> str:
    """Fallback: Simple keyword extraction (used when LLM is unavailable)"""
    import re
    
    # Extract Chinese words
    chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,}', product_description)
    
    # Filter out common meaningless words
    stop_words = ["product", "description", "suitable", "can", "able", "has", "provide", "include", "contain"]
    keywords = [word for word in chinese_words if word not in stop_words]
    
    # Take first 3-5 keywords
    keywords = keywords[:5]
    
    if keywords:
        return " ".join(keywords)
    else:
        # If extraction fails, return first 20 characters of product description
        return product_description[:20].strip()

async def _generate_reply_content_fallback(comment_content: str, product_description: str, username: str = "") -> str:
    """Fallback: Generate reply using templates (used when LLM is unavailable)"""
    import random
    
    product_summary = product_description[:30] if len(product_description) > 30 else product_description
    
    if username and username != "Unknown user":
        reply_templates = [
            f"Hi {username}, I saw your comment. I happen to have related {product_summary} that might help you. Feel free to DM me if you're interested~",
            f"Hey {username}, I have {product_summary} here that should help you. Contact me if you need more info~",
            f"Hello {username}, I have {product_summary} here. If you need it, feel free to DM me and I'll provide more details~",
        ]
    else:
        reply_templates = [
            f"Hi, I saw your comment. I happen to have related {product_summary} that might help you. Feel free to DM me if you're interested~",
            f"Hey, I have {product_summary} here that should help you. Contact me if you need more info~",
            f"Hello, I have {product_summary} here. If you need it, feel free to DM me and I'll provide more details~",
        ]
    
    reply = random.choice(reply_templates)
    
    if len(reply) > 100:
        reply = reply[:97] + "..."
    
    return reply

async def _get_note_comments_structured(url: str) -> List[Dict[str, Any]]:
    """Get post comments (returns structured data)
    
    Args:
        url: Post URL
    
    Returns:
        Comment list, each comment contains username, content, time, etc.
    """
    login_status = await ensure_browser()
    if not login_status:
        return []
    
    try:
        comment_start_time = time.time()
        print(f"[TIMING] Starting comment extraction stage - Getting comments from URL: {url}")
        
        # Stage 1: Navigate to post page
        nav_start = time.time()
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        nav_time = time.time() - nav_start
        print(f"[TIMING] Navigation to post page took: {nav_time:.2f}s")
        
        # Wait for page content to load - use wait_for_selector instead of fixed sleep
        wait_start = time.time()
        try:
            # Wait for post title or content to appear (max 3 seconds)
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
            wait_time = time.time() - wait_start
            print(f"[TIMING] Waiting for post content took: {wait_time:.2f}s")
        except:
            # Fallback: minimal wait
            await asyncio.sleep(0.5)
            wait_time = time.time() - wait_start
            print(f"[TIMING] Fallback wait took: {wait_time:.2f}s")
        
        # Stage 2: Wait for comment section
        comment_section_start = time.time()
        # Wait for comments section to load - Reddit uses shreddit-comment elements
        try:
            # Wait for comment section to appear
            await main_page.wait_for_selector('shreddit-comment', timeout=10000)
            comment_section_time = time.time() - comment_section_start
            print(f"[TIMING] Found comment section after: {comment_section_time:.2f}s")
        except:
            comment_section_time = time.time() - comment_section_start
            print(f"[TIMING] Comment section not found after {comment_section_time:.2f}s, trying alternative selectors...")

        # Stage 4: Extract comments
        extract_start = time.time()
        # Get comments using Reddit's actual selectors
        comments = []
        
        # Method 1: Use Reddit's shreddit-comment elements (new Reddit design)
        method1_start = time.time()
        try:
            # Reddit uses <shreddit-comment> custom elements
            comment_elements = await main_page.query_selector_all('shreddit-comment')
            method1_query_time = time.time() - method1_start
            print(f"[TIMING] Querying shreddit-comment elements took: {method1_query_time:.2f}s")
            print(f"Found {len(comment_elements)} shreddit-comment elements")
            
            # Process each comment element in parallel for better performance
            process_start = time.time()
            
            async def process_comment_element(element):
                """Process a single comment element and extract its data"""
                try:
                    # Get username - Reddit stores it in the 'author' attribute of shreddit-comment
                    username = "[deleted]"
                    try:
                        # First try to get from the author attribute
                        author_attr = await element.get_attribute('author')
                        if author_attr:
                            username = author_attr.strip()
                        else:
                            # Fallback: try to find username in shadow DOM or nested elements
                            username_selectors = [
                                'a[href*="/user/"]',
                                'a[href*="/u/"]',
                                'a.author',
                                '[data-testid="user-name"]',
                                'span:has-text("/u/")'
                            ]
                            
                            for username_selector in username_selectors:
                                try:
                                    username_el = await element.query_selector(username_selector)
                                    if username_el:
                                        username_text = await username_el.text_content()
                                        if username_text:
                                            username = username_text.strip()
                                            break
                                except:
                                    continue
                    except Exception as e:
                        print(f"Error getting username: {e}")
                    
                    # Get comment content - Reddit uses shadow DOM, so we need to access it differently
                    content = ""
                    try:
                        # Try to access shadow root content
                        try:
                            # Execute JavaScript to access shadow DOM
                            shadow_content = await element.evaluate("""
                                (el) => {
                                    const shadow = el.shadowRoot;
                                    if (shadow) {
                                        // Look for comment text in shadow DOM
                                        const textElements = shadow.querySelectorAll('div.md, div[class*="text"], p, div[class*="content"]');
                                        for (let elem of textElements) {
                                            const text = elem.textContent || elem.innerText;
                                            if (text && text.trim().length > 10) {
                                                return text.trim();
                                            }
                                        }
                                        // Fallback: get all text from shadow root
                                        return shadow.textContent || shadow.innerText || '';
                                    }
                                    return '';
                                }
                            """)
                            if shadow_content and len(shadow_content.strip()) > 0:
                                content = shadow_content.strip()
                        except:
                            pass
                        
                        # If shadow DOM access failed, try regular selectors
                        if not content:
                            content_selectors = [
                                'div.md',
                                'div[class*="text"]',
                                'div[class*="content"]',
                                'p',
                                'div.usertext-body',
                                'div.entry'
                            ]
                            
                            for content_selector in content_selectors:
                                try:
                                    content_el = await element.query_selector(content_selector)
                                    if content_el:
                                        content_text = await content_el.text_content()
                                        if content_text and len(content_text.strip()) > 10:
                                            content = content_text.strip()
                                            break
                                except:
                                    continue
                        
                        # Last resort: get all text from element
                        if not content:
                            full_text = await element.text_content()
                            if full_text:
                                # Remove username and common UI elements
                                cleaned_text = full_text.replace(username, "").strip()
                                # Remove common Reddit UI text
                                for remove_text in ["reply", "share", "report", "save", "permalink", "context", "give award"]:
                                    cleaned_text = cleaned_text.replace(remove_text, "").strip()
                                if len(cleaned_text) > 10:
                                    content = cleaned_text
                    except Exception as e:
                        print(f"Error extracting content: {e}")
                    
                    # Get comment time
                    time_location = "Unknown time"
                    try:
                        # Try to get from shadow DOM first
                        try:
                            time_text = await element.evaluate("""
                                (el) => {
                                    const shadow = el.shadowRoot;
                                    if (shadow) {
                                        const timeEl = shadow.querySelector('time, [data-testid*="timestamp"], a[href*="comment"]');
                                        if (timeEl) {
                                            return timeEl.getAttribute('title') || timeEl.textContent || '';
                                        }
                                    }
                                    return '';
                                }
                            """)
                            if time_text:
                                time_location = time_text.strip()
                        except:
                            pass
                        
                        # Fallback to regular selectors
                        if time_location == "Unknown time":
                            time_selectors = [
                                'time',
                                'a[href*="comment"]',
                                'span[class*="time"]',
                                '[data-testid*="timestamp"]'
                            ]
                            
                            for time_selector in time_selectors:
                                try:
                                    time_el = await element.query_selector(time_selector)
                                    if time_el:
                                        time_text = await time_el.get_attribute('title') or await time_el.text_content()
                                        if time_text:
                                            time_location = time_text.strip()
                                            break
                                except:
                                    continue
                    except:
                        pass
                    
                    # Return comment data if valid
                    if content and len(content.strip()) > 10:  # Minimum content length
                        return {
                            "Username": username,
                            "Content": content,
                            "Time": time_location
                        }
                    return None
                except Exception as e:
                    print(f"Error processing comment element: {e}")
                    return None
            
            # Process all comment elements in parallel
            comment_tasks = [process_comment_element(element) for element in comment_elements]
            comment_results = await asyncio.gather(*comment_tasks, return_exceptions=True)
            
            # Collect valid comments
            for result in comment_results:
                if isinstance(result, Exception):
                    continue
                if result is not None:
                    comments.append(result)
            
            if process_start:
                process_time = time.time() - process_start
                print(f"[TIMING] Processing {len(comment_elements)} comment elements in parallel took: {process_time:.2f}s")
        except Exception as e:
            method1_time = time.time() - method1_start
            print(f"[TIMING] Method 1 failed after {method1_time:.2f}s: {e}")
        
        # Method 2: Fallback to class-based selectors (old Reddit or alternative structure)
        if len(comments) == 0:
            method2_start = time.time()
            print("Trying fallback selectors...")
            try:
                # Try old Reddit selectors
                comment_elements = await main_page.query_selector_all('.comment, .Comment, [class*="comment"]')
                method2_query_time = time.time() - method2_start
                print(f"[TIMING] Querying fallback selectors took: {method2_query_time:.2f}s")
                print(f"Found {len(comment_elements)} comments using class-based selectors")
                
                # Process fallback comments
                fallback_process_start = time.time()
                
                for element in comment_elements:
                    try:
                        # Get username
                        username = "[deleted]"
                        try:
                            username_el = await element.query_selector('a.author, a[class*="author"]')
                            if username_el:
                                username_text = await username_el.text_content()
                                if username_text:
                                    username = username_text.strip()
                        except:
                            pass
                        
                        # Get content
                        content = ""
                        try:
                            content_el = await element.query_selector('.md, .usertext-body, p')
                            if content_el:
                                content_text = await content_el.text_content()
                                if content_text:
                                    content = content_text.strip()
                        except:
                            # Fallback to element text
                            try:
                                full_text = await element.text_content()
                                if full_text:
                                    content = full_text.strip()
                            except:
                                pass
                        
                        # Get time
                        time_location = "Unknown time"
                        try:
                            time_el = await element.query_selector('time, .live-timestamp')
                            if time_el:
                                time_text = await time_el.get_attribute('title') or await time_el.text_content()
                                if time_text:
                                    time_location = time_text.strip()
                        except:
                            pass
                        
                        if content and len(content.strip()) > 0:
                            comments.append({
                                "Username": username,
                                "Content": content,
                                "Time": time_location
                            })
                    except Exception as e:
                        print(f"Error processing fallback comment: {e}")
                        continue
                
                fallback_process_time = time.time() - fallback_process_start
                print(f"[TIMING] Processing {len(comment_elements)} fallback comments took: {fallback_process_time:.2f}s")
            except Exception as e:
                method2_time = time.time() - method2_start
                print(f"[TIMING] Fallback method failed after {method2_time:.2f}s: {e}")
        
        extract_time = time.time() - extract_start
        print(f"[TIMING] Total comment extraction time: {extract_time:.2f}s")
        print(f"Total comments extracted: {len(comments)}")
        
        comment_total_time = time.time() - comment_start_time
        print(f"[TIMING] Total comment stage time: {comment_total_time:.2f}s")
        return comments
    
    except Exception as e:
        print(f"Error getting comments: {str(e)}")
        return []

async def _generate_smart_comment(post_content, comment_type):
    """Generate smart comment based on post content and comment type"""
    title = post_content.get("Title", "")
    content = post_content.get("Content", "")
    author = post_content.get("Author", "")
    
    # Extract post keywords
    keywords = []
    
    # Simple word segmentation
    import re
    words = re.findall(r'\w+', f"{title} {content}")
    
    # Use common popular domain keywords
    domain_keywords = {
        "beauty": ["makeup", "cosmetics", "skincare", "beauty", "lipstick", "foundation", "moisturizer"],
        "fashion": ["fashion", "outfit", "style", "clothing", "wardrobe", "trend"],
        "food": ["food", "recipe", "restaurant", "cooking", "baking", "cuisine"],
        "travel": ["travel", "trip", "destination", "guide", "vacation", "hotel"],
        "parenting": ["baby", "parenting", "children", "toddler", "toys"],
        "tech": ["tech", "phone", "computer", "camera", "smart", "device"],
        "home": ["home", "decor", "furniture", "design", "interior"],
        "fitness": ["fitness", "workout", "exercise", "training", "gym"]
    }
    
    # Detect which domain the post might belong to
    detected_domains = []
    for domain, domain_keys in domain_keywords.items():
        for key in domain_keys:
            if key in title.lower() or key in content.lower():
                detected_domains.append(domain)
                break
    
    # If no clear domain detected, default to lifestyle
    if not detected_domains:
        detected_domains = ["lifestyle"]
    
    # Generate comment templates based on comment type
    templates = {
        "lead_gen": [
            f"This {detected_domains[0]} share is great! I'm also researching related content, feel free to DM me~",
            f"Thanks for sharing, {author}'s insights are unique! I've also compiled some related materials, interested to chat?",
            f"Your share is very insightful! I've written similar content, feel free to reach out",
            f"Really like your sharing style! I also do {detected_domains[0]} related content, we can follow each other",
            f"Totally relate! I've encountered similar situations, DM me if you want to know more",
            f"This post has so much info! Saved it, we can discuss if you have questions~"
        ],
        "like": [
            f"Awesome! {author}'s shares are always so practical",
            f"Every time I see {author}'s shares I learn something, keep it up!",
            f"This content is super detailed, learned a lot, thanks for sharing!",
            f"Love this in-depth share, much more meaningful than typical {detected_domains[0]} posts",
            f"Saved and upvoted, very valuable reference",
            f"This kind of high-quality content is rare, thanks for sharing"
        ],
        "consult": [
            f"Hey OP, any beginner tips for {detected_domains[0]}?",
            f"This {detected_domains[0]} technique looks practical, is it suitable for beginners?",
            f"OP's shared experience is so valuable, can you elaborate on how you got started?",
            f"Very inspiring, would like to ask {author}, how did you reach such a professional level?",
            f"Very interested in this field, any recommended learning resources to share?",
            f"OP's insights are unique, could you share your learning path?"
        ],
        "professional": [
            f"As a {detected_domains[0]} practitioner, I agree with OP's points, especially about {title[:10]}",
            f"From a professional perspective, this share covers key points, I'd like to add...",
            f"This analysis is spot on, I've found similar patterns in practice, totally agree",
            f"Very professional share! I've been in related work for years, these methods really work",
            f"The depth of this content is impressive, shows OP's professional expertise",
            f"From a technical perspective, the methods OP shared are very feasible, worth trying"
        ]
    }
    
    import random
    
    # Ensure comment type is valid
    if comment_type not in templates:
        comment_type = "lead_gen"  # Default to lead_gen template
    
    # Randomly select a template
    selected_template = random.choice(templates[comment_type])
    
    # If professional type comment, can add some industry terms
    if comment_type == "professional":
        domain_terms = {
            "beauty": ["finish", "texture", "pigmentation", "longevity", "application"],
            "fashion": ["fit", "cut", "silhouette", "layering", "color palette"],
            "food": ["flavor", "texture", "technique", "temperature", "seasoning"],
            "travel": ["itinerary", "guide", "experience", "local culture", "hidden spots"],
            "parenting": ["early education", "development", "nutrition", "interaction"],
            "tech": ["performance", "experience", "specs", "compatibility", "efficiency"],
            "home": ["space planning", "lighting", "color scheme", "functional areas"],
            "fitness": ["training plan", "sets", "intensity", "recovery", "metabolism"]
        }
        
        # Randomly add a term for each detected domain
        for domain in detected_domains:
            if domain in domain_terms:
                terms = domain_terms[domain]
                selected_term = random.choice(terms)
                if random.random() > 0.5:  # 50% chance to add term
                    selected_template += f", especially insights on {selected_term} are unique"
    
    # Add DM-attracting endings to some comments
    if comment_type == "lead_gen" or (comment_type == "consult" and random.random() > 0.7):
        endings = [
            "Feel free to DM me if you have more questions~",
            "Check out my profile if you're interested",
            "DM me if you want to know more",
            "Follow me for more related content",
            "DM me for surprises~"
        ]
        selected_template += " " + random.choice(endings)
    
    return selected_template

@mcp.tool()
async def reply_to_comment(url: str, comment_content: str, reply_text: str) -> str:
    """Reply to specified comment
    
    Args:
        url: Post URL
        comment_content: Comment content to reply to (used to locate comment)
        reply_text: Reply text
    """
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first to reply to comments"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Wait for post content to appear instead of fixed sleep
        try:
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
        except:
            await asyncio.sleep(1)  # Minimal fallback
        
        # Scroll to comment section
        comment_section_locators = [
            main_page.get_by_text("comments", exact=False),
            main_page.get_by_text("comment", exact=False),
            main_page.locator("text=comment").first
        ]
        
        for locator in comment_section_locators:
            try:
                if await locator.count() > 0:
                    await locator.scroll_into_view_if_needed(timeout=5000)
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue
        
        # Scroll page to load more comments
        for i in range(5):
            try:
                await main_page.evaluate("window.scrollBy(0, 500)")
                # Reduced wait for scroll
                await asyncio.sleep(0.3)
            except Exception:
                pass
        
        # Find comment containing specified content
        comment_found = False
        comment_selectors = [
            "div.comment-item", 
            "div.commentItem",
            "div.comment-content",
            "div.comment-wrapper",
            "section.comment",
            "div.feed-comment"
        ]
        
        for selector in comment_selectors:
            comment_elements = main_page.locator(selector)
            count = await comment_elements.count()
            if count > 0:
                for i in range(count):
                    try:
                        comment_element = comment_elements.nth(i)
                        element_text = await comment_element.text_content()
                        
                        # Check if contains target comment content
                        if comment_content in element_text or element_text in comment_content:
                            # Found target comment, try to find reply button
                            reply_button = None
                            
                            # Try multiple ways to find reply button
                            reply_selectors = [
                                comment_element.locator("text=Reply").first,
                                comment_element.locator("button:has-text('Reply')").first,
                                comment_element.locator("span:has-text('Reply')").first,
                                comment_element.locator("a:has-text('Reply')").first,
                            ]
                            
                            for reply_selector in reply_selectors:
                                try:
                                    if await reply_selector.count() > 0 and await reply_selector.is_visible():
                                        reply_button = reply_selector
                                        break
                                except Exception:
                                    continue
                            
                            # If reply button not found, try using JavaScript to find
                            if not reply_button:
                                reply_button_handle = await main_page.evaluate('''
                                    (commentElement) => {
                                        // Find button or link containing "Reply" text
                                        const allElements = commentElement.querySelectorAll('*');
                                        for (let el of allElements) {
                                            const text = el.textContent || '';
                                            if (text.includes('Reply') && (el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'SPAN')) {
                                                return el;
                                            }
                                        }
                                        return null;
                                    }
                                ''', await comment_element.element_handle())
                                
                                if reply_button_handle:
                                    reply_button = main_page.locator(f"xpath=//*[contains(text(), 'Reply')]").first
                            
                            if reply_button:
                                # Scroll to reply button
                                await reply_button.scroll_into_view_if_needed()
                                # Wait for button to be ready
                                try:
                                    await reply_button.wait_for(state="visible", timeout=500)
                                except:
                                    await asyncio.sleep(0.2)
                                
                                # Click reply button
                                await reply_button.click()
                                # Wait for reply input to appear instead of fixed sleep
                                try:
                                    await main_page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=1500)
                                except:
                                    await asyncio.sleep(0.5)  # Reduced fallback
                                
                                # Find reply input box
                                reply_input = None
                                reply_input_selectors = [
                                    'div[contenteditable="true"]',
                                    'textarea',
                                    'input[type="text"]',
                                    'text="Add a comment..."',
                                ]
                                
                                for input_selector in reply_input_selectors:
                                    try:
                                        input_element = await main_page.query_selector(input_selector)
                                        if input_element and await input_element.is_visible():
                                            reply_input = input_element
                                            break
                                    except Exception:
                                        continue
                                
                                if reply_input:
                                    # Click input box
                                    await reply_input.click()
                                    # Wait for input to be focused
                                    try:
                                        await reply_input.wait_for(state="visible", timeout=300)
                                    except:
                                        await asyncio.sleep(0.1)
                                    
                                    # Type reply content
                                    await main_page.keyboard.type(reply_text, delay=30)  # Reduced delay
                                    await asyncio.sleep(0.3)  # Reduced wait
                                    
                                    # Send reply
                                    send_button = None
                                    send_selectors = [
                                        'button:has-text("Comment")',
                                        'button:has-text("Reply")',
                                        'button[type="submit"]',
                                    ]
                                    
                                    for send_selector in send_selectors:
                                        try:
                                            send_el = await main_page.query_selector(send_selector)
                                            if send_el and await send_el.is_visible():
                                                send_button = send_el
                                                break
                                        except Exception:
                                            continue
                                    
                                    if send_button:
                                        await send_button.click()
                                    else:
                                        # Try using Enter key to send
                                        await main_page.keyboard.press('Enter')
                                    
                                    # Wait for reply to be posted - check for success instead of fixed sleep
                                    try:
                                        await main_page.wait_for_selector('button:has-text("Reply"), button[aria-label*="reply"]', timeout=2000, state="hidden")
                                    except:
                                        await asyncio.sleep(1)  # Reduced fallback
                                    comment_found = True
                                    return f"Successfully replied to comment: {reply_text}"
                                
                                else:
                                    return "Found comment but unable to locate reply input box"
                            else:
                                return "Found comment but unable to find reply button"
                    except Exception as e:
                        continue
                
                if comment_found:
                    break
        
        if not comment_found:
            return f"Comment containing \"{comment_content[:20]}...\" not found, unable to reply"
    
    except Exception as e:
        return f"Error replying to comment: {str(e)}"

@mcp.tool()
async def generate_search_keywords(product_description: str) -> str:
    """Intelligently generate search keywords based on product description
    
    Args:
        product_description: Product description
    
    Returns:
        Generated search keywords
    """
    keywords = await _generate_search_keywords(product_description)
    return f"Search keywords generated from product description: {keywords}"

@mcp.tool()
async def auto_promote_product(product_description: str, search_keywords: str = "", max_posts: int = 5, min_match_score: float = 40.0) -> str:
    """Auto promote product: search related posts, analyze comments, reply to users who need the product
    
    Args:
        product_description: Product description
        search_keywords: Search keywords (optional, auto-generated if not provided)
        max_posts: Maximum number of posts to process (default 5)
        min_match_score: Minimum match score (default 40.0)
    
    Returns:
        Execution result report
    """
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first"
    
    # If search keywords not provided, auto-generate
    if not search_keywords or search_keywords.strip() == "":
        search_keywords = await _generate_search_keywords(product_description)
    
    results = {
        "SearchedPosts": 0,
        "AnalyzedComments": 0,
        "MatchedComments": 0,
        "SuccessfulReplies": 0,
        "FailedReplies": [],
        "MatchedCommentDetails": [],
        "SearchKeywords": search_keywords
    }
    
    try:
        # 1. Search related posts
        search_url = f"https://www.reddit.com/search/?q={search_keywords}"
        await main_page.goto(search_url, timeout=60000)
        await asyncio.sleep(5)
        
        # Get post links
        post_elements = await main_page.query_selector_all('a[href*="/r/"]')
        post_links = []
        seen_urls = set()
        
        for element in post_elements:
            href = await element.get_attribute('href')
            if href and '/r/' in href:
                full_url = f"https://www.reddit.com{href}" if not href.startswith('http') else href
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    post_links.append(full_url)
                    if len(post_links) >= max_posts:
                        break
        
        results["SearchedPosts"] = len(post_links)
        
        if not post_links:
            return f"No posts found related to \"{search_keywords}\""
        
        # 2. Iterate through each post, analyze comments
        for post_url in post_links:
            try:
                # Get comments
                comments = await _get_note_comments_structured(post_url)
                results["AnalyzedComments"] += len(comments)
                
                # Analyze each comment
                for comment in comments:
                    comment_content = comment.get("Content", "")
                    username = comment.get("Username", "")
                    
                    if not comment_content or len(comment_content) < 5:
                        continue
                    
                    # Analyze match score
                    match_result = await _analyze_comment_match(comment_content, product_description)
                    
                    if match_result["needs_product"] and match_result["match_score"] >= min_match_score:
                        results["MatchedComments"] += 1
                        
                        # Generate reply content
                        reply_text = await _generate_reply_content(comment_content, product_description, username)
                        
                        # Record matched comment
                        results["MatchedCommentDetails"].append({
                            "Post": post_url,
                            "User": username,
                            "Comment": comment_content[:50] + "...",
                            "MatchScore": match_result["match_score"],
                            "Reply": reply_text
                        })
                        
                        # Try to reply
                        try:
                            reply_result = await reply_to_comment(post_url, comment_content, reply_text)
                            if "success" in reply_result.lower():
                                results["SuccessfulReplies"] += 1
                            else:
                                results["FailedReplies"].append({
                                    "User": username,
                                    "Reason": reply_result
                                })
                        except Exception as e:
                            results["FailedReplies"].append({
                                "User": username,
                                "Reason": f"Error replying: {str(e)}"
                            })
                        
                        # Avoid replying too fast, add minimal delay (reduced from 5s)
                        await asyncio.sleep(2)
                
                # Add minimal delay after processing each post (reduced from 3s)
                await asyncio.sleep(1)
            
            except Exception as e:
                continue
        
        # Generate report
        report = f"""
Auto promotion product execution completed!

Product description: {product_description[:50]}...
Search keywords: {results['SearchKeywords']}

Execution statistics:
- Searched posts: {results['SearchedPosts']}
- Analyzed comments: {results['AnalyzedComments']}
- Matched comments: {results['MatchedComments']}
- Successful replies: {results['SuccessfulReplies']}
- Failed replies: {len(results['FailedReplies'])}

"""
        
        if results["MatchedCommentDetails"]:
            report += "\nMatched comment details:\n"
            for i, detail in enumerate(results["MatchedCommentDetails"][:10], 1):  # Show max 10
                report += f"\n{i}. User: {detail['User']}\n"
                report += f"   Comment: {detail['Comment']}\n"
                report += f"   Match score: {detail['MatchScore']:.1f}\n"
                report += f"   Reply: {detail['Reply']}\n"
        
        if results["FailedReplies"]:
            report += "\nFailed replies:\n"
            for i, fail in enumerate(results["FailedReplies"][:5], 1):  # Show max 5
                report += f"{i}. {fail['User']}: {fail['Reason']}\n"
        
        return report
    
    except Exception as e:
        return f"Error auto promoting product: {str(e)}"

# Export original functions for use by app.py (bypass MCP decorator)
# These functions can be called directly, won't be wrapped by MCP decorator
__all__ = [
    'login_impl',
    'search_notes_impl', 
    'get_note_content_impl',
    'get_note_comments',
    'reply_to_comment',
    'generate_search_keywords',
    'auto_promote_product',
    'ensure_browser'
]

# Create original implementation versions for other functions
async def get_note_comments_impl(url: str) -> str:
    """Get post comments (original implementation)"""
    # Directly call internal implementation
    from service_mcp import _get_note_comments_structured
    comments = await _get_note_comments_structured(url)
    if comments:
        result = f"Found {len(comments)} comments:\n\n"
        for i, comment in enumerate(comments, 1):
            result += f"{i}. {comment['Username']} ({comment['Time']}): {comment['Content']}\n\n"
        return result
    else:
        return "No comments found. The post may have no comments or the comment section is inaccessible."

async def reply_to_comment_impl(url: str, comment_content: str, reply_text: str) -> str:
    """Reply to specified comment (original implementation)"""
    global main_page
    
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first to reply to comments"
    
    # Ensure main_page is valid
    if main_page is None:
        return "Browser page not initialized, please retry"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000)
        await asyncio.sleep(5)
        
        # Scroll to comment section
        comment_section_locators = [
            main_page.get_by_text("comments", exact=False),
            main_page.get_by_text("comment", exact=False),
            main_page.locator("text=comment").first
        ]
        
        for locator in comment_section_locators:
            try:
                if await locator.count() > 0:
                    await locator.scroll_into_view_if_needed(timeout=5000)
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue
        
        # Scroll page to load more comments
        for i in range(5):
            try:
                await main_page.evaluate("window.scrollBy(0, 500)")
                # Reduced wait for scroll
                await asyncio.sleep(0.3)
            except Exception:
                pass
        
        # Find comment containing specified content
        comment_found = False
        comment_selectors = [
            "div.comment-item", 
            "div.commentItem",
            "div.comment-content",
            "div.comment-wrapper",
            "section.comment",
            "div.feed-comment"
        ]
        
        for selector in comment_selectors:
            comment_elements = main_page.locator(selector)
            count = await comment_elements.count()
            if count > 0:
                for i in range(count):
                    try:
                        comment_element = comment_elements.nth(i)
                        element_text = await comment_element.text_content()
                        
                        # Check if contains target comment content
                        if comment_content in element_text or element_text in comment_content:
                            # Found target comment, try to find reply button
                            reply_button = None
                            
                            # Try multiple ways to find reply button
                            reply_selectors = [
                                comment_element.locator("text=Reply").first,
                                comment_element.locator("button:has-text('Reply')").first,
                                comment_element.locator("span:has-text('Reply')").first,
                                comment_element.locator("a:has-text('Reply')").first,
                            ]
                            
                            for reply_selector in reply_selectors:
                                try:
                                    if await reply_selector.count() > 0 and await reply_selector.is_visible():
                                        reply_button = reply_selector
                                        break
                                except Exception:
                                    continue
                            
                            if reply_button:
                                # Scroll to reply button
                                await reply_button.scroll_into_view_if_needed()
                                # Wait for button to be ready
                                try:
                                    await reply_button.wait_for(state="visible", timeout=500)
                                except:
                                    await asyncio.sleep(0.2)
                                
                                # Click reply button
                                await reply_button.click()
                                # Wait for reply input to appear instead of fixed sleep
                                try:
                                    await main_page.wait_for_selector('textarea, div[contenteditable="true"]', timeout=1500)
                                except:
                                    await asyncio.sleep(0.5)  # Reduced fallback
                                
                                # Find reply input box
                                reply_input = None
                                reply_input_selectors = [
                                    'div[contenteditable="true"]',
                                    'textarea',
                                    'input[type="text"]',
                                    'text="Add a comment..."',
                                ]
                                
                                for input_selector in reply_input_selectors:
                                    try:
                                        input_element = await main_page.query_selector(input_selector)
                                        if input_element and await input_element.is_visible():
                                            reply_input = input_element
                                            break
                                    except Exception:
                                        continue
                                
                                if reply_input:
                                    # Click input box
                                    await reply_input.click()
                                    # Wait for input to be focused
                                    try:
                                        await reply_input.wait_for(state="visible", timeout=300)
                                    except:
                                        await asyncio.sleep(0.1)
                                    
                                    # Type reply content
                                    await main_page.keyboard.type(reply_text, delay=30)  # Reduced delay
                                    await asyncio.sleep(0.3)  # Reduced wait
                                    
                                    # Send reply
                                    send_button = None
                                    send_selectors = [
                                        'button:has-text("Comment")',
                                        'button:has-text("Reply")',
                                        'button[type="submit"]',
                                    ]
                                    
                                    for send_selector in send_selectors:
                                        try:
                                            send_el = await main_page.query_selector(send_selector)
                                            if send_el and await send_el.is_visible():
                                                send_button = send_el
                                                break
                                        except Exception:
                                            continue
                                    
                                    if send_button:
                                        await send_button.click()
                                    else:
                                        # Try using Enter key to send
                                        await main_page.keyboard.press('Enter')
                                    
                                    # Wait for reply to be posted - check for success instead of fixed sleep
                                    try:
                                        await main_page.wait_for_selector('button:has-text("Reply"), button[aria-label*="reply"]', timeout=2000, state="hidden")
                                    except:
                                        await asyncio.sleep(1)  # Reduced fallback
                                    comment_found = True
                                    return f"Successfully replied to comment: {reply_text}"
                                
                                else:
                                    return "Found comment but unable to locate reply input box"
                            else:
                                return "Found comment but unable to find reply button"
                    except Exception as e:
                        continue
                
                if comment_found:
                    break
        
        if not comment_found:
            return f"Comment containing \"{comment_content[:20]}...\" not found, unable to reply"
    
    except Exception as e:
        return f"Error replying to comment: {str(e)}"

async def generate_search_keywords_impl(product_description: str) -> str:
    """Intelligently generate search keywords based on product description (original implementation)"""
    keywords = await _generate_search_keywords(product_description)
    return f"Search keywords generated from product description: {keywords}"

async def post_smart_comment_impl(url: str, comment_type: str = "lead_gen", comment_text: Optional[str] = None) -> str:
    """Post smart comment based on post content (original implementation, unwrapped from @mcp.tool())
    
    Args:
        url: Post URL
        comment_type: Comment type (lead_gen, like, consult, professional)
        comment_text: Optional pre-generated comment text. If provided, skips content fetching and comment generation.
    """
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first to post comments"
    
    try:
        # Visit post link
        await main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Wait for post content to appear instead of fixed sleep
        try:
            await main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
        except:
            await asyncio.sleep(1)  # Minimal fallback
        
        # If comment_text is provided, skip content fetching and generation
        if comment_text and comment_text.strip():
            # Use the provided comment text directly
            final_comment_text = comment_text.strip()
        else:
            # Get post content for analysis
            post_content = {}
            
            # Get post title
            try:
                title_selectors = [
                    'h1[data-testid="post-title"]',
                    'h1',
                    '[data-testid="post-title"]',
                    'a[data-testid="post-title"]'
                ]
                for selector in title_selectors:
                    try:
                        title_element = await main_page.query_selector(selector)
                        if title_element:
                            title = await title_element.text_content()
                            if title and title.strip():
                                post_content["Title"] = title.strip()
                                break
                    except:
                        continue
                if "Title" not in post_content:
                    post_content["Title"] = "Unknown title"
            except Exception:
                post_content["Title"] = "Unknown title"
            
            # Get author
            try:
                author_selectors = [
                    'a[data-testid="post_author_link"]',
                    'a[href*="/user/"]',
                    'a[href*="/u/"]'
                ]
                for selector in author_selectors:
                    try:
                        author_element = await main_page.query_selector(selector)
                        if author_element:
                            author = await author_element.text_content()
                            if author and author.strip():
                                post_content["Author"] = author.strip()
                                break
                    except:
                        continue
                if "Author" not in post_content:
                    post_content["Author"] = "Unknown author"
            except Exception:
                post_content["Author"] = "Unknown author"
            
            # Get post body content
            try:
                content_selectors = [
                    'div[data-testid="post-content"]',
                    'div.md',
                    'article',
                    'div[data-testid="comment"]'
                ]
                
                post_content["Content"] = "Failed to get content"
                for selector in content_selectors:
                    try:
                        content_element = await main_page.query_selector(selector)
                        if content_element:
                            content_text = await content_element.text_content()
                            if content_text and len(content_text.strip()) > 10:
                                post_content["Content"] = content_text.strip()
                                break
                    except:
                        continue
                
                # Use JavaScript to extract main text content
                if post_content["Content"] == "Failed to get content":
                    content_text = await main_page.evaluate('''
                        () => {
                            const contentElements = Array.from(document.querySelectorAll('div, p, article'))
                                .filter(el => {
                                    const text = el.textContent.trim();
                                    return text.length > 50 && text.length < 5000 &&
                                        el.querySelectorAll('a, button').length < 5 &&
                                        el.children.length < 10;
                                })
                                .sort((a, b) => b.textContent.length - a.textContent.length);
                            
                            if (contentElements.length > 0) {
                                return contentElements[0].textContent.trim();
                            }
                            
                            return null;
                        }
                    ''')
                    
                    if content_text:
                        post_content["Content"] = content_text
            except Exception:
                post_content["Content"] = "Failed to get content"
            
            # Generate smart comment based on post content and comment type
            final_comment_text = await _generate_smart_comment(post_content, comment_type)
        
        # Locate comment input box based on page snapshot
        # Locate comment area first
        try:
            # Try to find comment count area first, it usually contains "comments" text
            comment_count_selectors = [
                'text="comments"',
                'text="comment"',
                'text=/\\d+ comments/',
            ]
            
            for selector in comment_count_selectors:
                try:
                    comment_count_element = await main_page.query_selector(selector)
                    if comment_count_element:
                        await comment_count_element.scroll_into_view_if_needed()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue
                
            # Locate comment input box
            input_box_selectors = [
                'paragraph:has-text("Add a comment...")',
                'text="Add a comment..."',
                'text="What are your thoughts?"',
                'div[contenteditable="true"]',
                'textarea[placeholder*="comment"]'
            ]
            
            comment_input = None
            for selector in input_box_selectors:
                try:
                    input_element = await main_page.query_selector(selector)
                    if input_element and await input_element.is_visible():
                        await input_element.scroll_into_view_if_needed()
                        await asyncio.sleep(1)
                        comment_input = input_element
                        break
                except Exception:
                    continue
                    
            # If all above methods failed, try using JavaScript to find
            if not comment_input:
                comment_input = await main_page.evaluate('''
                    () => {
                        // Find elements containing "Add a comment" or similar
                        const elements = Array.from(document.querySelectorAll('*'))
                            .filter(el => el.textContent && (
                                el.textContent.includes('Add a comment') ||
                                el.textContent.includes('What are your thoughts')
                            ));
                        if (elements.length > 0) return elements[0];
                        
                        // Find editable div elements
                        const editableDivs = Array.from(document.querySelectorAll('div[contenteditable="true"]'));
                        if (editableDivs.length > 0) return editableDivs[0];
                        
                        return null;
                    }
                ''')
                
                if comment_input:
                    comment_input = await main_page.query_selector_all('*')[-1]  # Use last element as placeholder
            
            if not comment_input:
                return "Unable to find comment input box, cannot post comment"
            
            # Click comment input box
            await comment_input.click()
            # Wait for input to be focused/ready instead of fixed sleep
            try:
                await comment_input.wait_for(state="visible", timeout=500)
            except:
                await asyncio.sleep(0.2)  # Minimal wait for focus
            
            # Type comment content using keyboard
            await main_page.keyboard.type(final_comment_text, delay=30)  # Reduced delay
            # Reduced wait after typing
            await asyncio.sleep(0.3)
            
            # Try to send using Enter key
            try:
                # Look for send button
                send_button_selectors = [
                    'button:has-text("Comment")',
                    'button:has-text("Post")',
                    'button[type="submit"]'
                ]
                
                send_button = None
                for selector in send_button_selectors:
                    elements = await main_page.query_selector_all(selector)
                    for element in elements:
                        text_content = await element.text_content()
                        if text_content and ('Comment' in text_content or 'Post' in text_content):
                            send_button = element
                            break
                    if send_button:
                        break
                
                if send_button:
                    await send_button.click()
                else:
                    # If send button not found, use Enter key
                    await main_page.keyboard.press('Enter')
                
                await asyncio.sleep(3)  # Wait for comment to be sent
                
                return f"Successfully posted comment: {final_comment_text}"
            except Exception as e:
                # If clicking send button failed, try sending via Enter key
                try:
                    await main_page.keyboard.press('Enter')
                    await asyncio.sleep(3)
                    return f"Comment sent via Enter key: {final_comment_text}"
                except Exception as press_error:
                    return f"Error trying to send comment: {str(e)}, Enter key also failed: {str(press_error)}"
                
        except Exception as e:
            return f"Error operating comment section: {str(e)}"
    
    except Exception as e:
        return f"Error posting comment: {str(e)}"

async def _get_or_generate_keywords(product_description: str, search_keywords: str) -> str:
    """Get or generate search keywords (helper function)"""
    if not search_keywords or search_keywords.strip() == "":
        return await _generate_search_keywords(product_description)
    return search_keywords.strip()

async def _search_and_get_post_links(keywords: str, max_posts: int) -> list:
    """Search and get post links (helper function)"""
    global main_page
    
    search_url = f"https://www.reddit.com/search/?q={keywords}"
    await main_page.goto(search_url, timeout=60000)
    await asyncio.sleep(5)
    
    post_elements = await main_page.query_selector_all('a[href*="/r/"]')
    post_links = []
    seen_urls = set()
    
    for element in post_elements:
        href = await element.get_attribute('href')
        if href and '/r/' in href:
            full_url = f"https://www.reddit.com{href}" if not href.startswith('http') else href
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                post_links.append(full_url)
                if len(post_links) >= max_posts:
                    break
    
    return post_links

async def _analyze_and_match_comments(
    post_url: str, 
    product_description: str, 
    min_match_score: float
) -> Tuple[List[Dict], List[Dict]]:
    """Analyze comments and return all comments and matched comments (helper function)"""
    comments = await _get_note_comments_structured(post_url)
    matched_comments = []
    
    for comment in comments:
        comment_content = comment.get("Content", "")
        username = comment.get("Username", "")
        
        if not comment_content or len(comment_content) < 5:
            continue
        
        match_result = await _analyze_comment_match(comment_content, product_description)
        
        if match_result["needs_product"] and match_result["match_score"] >= min_match_score:
            reply_text = await _generate_reply_content(comment_content, product_description, username)
            
            matched_comments.append({
                "post_url": post_url,
                "username": username,
                "comment": comment_content,
                "match_score": match_result["match_score"],
                "reply_text": reply_text
            })
    
    return comments, matched_comments

async def step_by_step_promote_impl(
    product_description: str,
    search_keywords: str = "",
    max_posts: int = 5,
    min_match_score: float = 40.0,
    step: str = "generate_keywords"
) -> dict:
    """
    Promote product step by step, return intermediate results for each step
    
    Args:
        product_description: Product description
        search_keywords: Search keywords (auto-generated if empty)
        max_posts: Maximum number of posts to process
        min_match_score: Minimum match score
        step: Current execution step
            - "generate_keywords": Generate keywords
            - "search_notes": Search posts
            - "analyze_comments": Analyze comments
            - "generate_replies": Generate replies
            - "send_replies": Send replies
    
    Returns:
        dict: Dictionary containing step information, status and results
    """
    global main_page
    
    result = {
        "step": step,
        "status": "success",
        "message": "",
        "data": {}
    }
    
    try:
        login_status = await ensure_browser()
        if not login_status:
            result["status"] = "error"
            result["message"] = "Please login to Reddit account first"
            return result
        
        if main_page is None:
            result["status"] = "error"
            result["message"] = "Browser page not initialized, please retry"
            return result
        
        # Get or generate keywords (needed for all steps)
        keywords = await _get_or_generate_keywords(product_description, search_keywords)
        
        if step == "generate_keywords":
            # Step 1: Generate search keywords
            result["data"] = {
                "keywords": keywords,
                "product_description": product_description
            }
            result["message"] = f"✅ Generated search keywords: {keywords}"
            result["next_step"] = "search_notes"
            
        elif step == "search_notes":
            # Step 2: Search posts
            post_links = await _search_and_get_post_links(keywords, max_posts)
            
            if not post_links:
                result["status"] = "error"
                result["message"] = f"No posts found related to \"{keywords}\""
                return result
            
            result["data"] = {
                "keywords": keywords,
                "post_count": len(post_links),
                "post_links": post_links
            }
            result["message"] = f"✅ Found {len(post_links)} related posts"
            result["next_step"] = "analyze_comments"
            
        elif step == "analyze_comments":
            # Step 3: Analyze comments
            post_links = await _search_and_get_post_links(keywords, max_posts)
            
            # Analyze comments from all posts
            all_comments = []
            matched_comments = []
            
            for post_url in post_links:
                try:
                    comments, matched = await _analyze_and_match_comments(
                        post_url, product_description, min_match_score
                    )
                    all_comments.extend(comments)
                    matched_comments.extend(matched)
                    await asyncio.sleep(2)
                except Exception as e:
                    continue
            
            result["data"] = {
                "total_comments": len(all_comments),
                "matched_comments": matched_comments,
                "matched_count": len(matched_comments)
            }
            result["message"] = f"✅ Analyzed {len(all_comments)} comments, found {len(matched_comments)} matched comments"
            result["next_step"] = "send_replies" if matched_comments else "complete"
            
        elif step == "send_replies":
            # Step 4: Send replies
            post_links = await _search_and_get_post_links(keywords, max_posts)
            
            success_count = 0
            failed_count = 0
            reply_results = []
            
            for post_url in post_links:
                try:
                    _, matched_comments = await _analyze_and_match_comments(
                        post_url, product_description, min_match_score
                    )
                    
                    for matched in matched_comments:
                        try:
                            reply_result = await reply_to_comment_impl(
                                matched["post_url"], 
                                matched["comment"], 
                                matched["reply_text"]
                            )
                            if "success" in reply_result.lower():
                                success_count += 1
                                reply_results.append({
                                    "username": matched["username"],
                                    "status": "success",
                                    "reply": matched["reply_text"]
                                })
                            else:
                                failed_count += 1
                                reply_results.append({
                                    "username": matched["username"],
                                    "status": "failed",
                                    "reason": reply_result
                                })
                        except Exception as e:
                            failed_count += 1
                            reply_results.append({
                                "username": matched["username"],
                                "status": "failed",
                                "reason": f"Error replying: {str(e)}"
                            })
                        
                        # Reduced delay to avoid rate limiting (from 5s to 2s)
                        await asyncio.sleep(2)
                    
                    # Reduced delay after processing (from 3s to 1s)
                    await asyncio.sleep(1)
                except Exception as e:
                    continue
            
            result["data"] = {
                "success_count": success_count,
                "failed_count": failed_count,
                "reply_results": reply_results
            }
            result["message"] = f"✅ Sent {success_count} replies, {failed_count} failed"
            result["next_step"] = "complete"
            
        else:
            result["status"] = "error"
            result["message"] = f"Unknown step: {step}"
            
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Error executing step {step}: {str(e)}"
    
    return result

async def auto_promote_product_impl(product_description: str, search_keywords: str = "", max_posts: int = 5, min_match_score: float = 40.0) -> str:
    """Auto promote product (original implementation)"""
    global main_page
    
    login_status = await ensure_browser()
    if not login_status:
        return "Please login to Reddit account first"
    
    # Ensure main_page is valid
    if main_page is None:
        return "Browser page not initialized, please retry"
    
    # If search keywords not provided, auto-generate
    if not search_keywords or search_keywords.strip() == "":
        search_keywords = await _generate_search_keywords(product_description)
    
    results = {
        "SearchedPosts": 0,
        "AnalyzedComments": 0,
        "MatchedComments": 0,
        "SuccessfulReplies": 0,
        "FailedReplies": [],
        "MatchedCommentDetails": [],
        "SearchKeywords": search_keywords
    }
    
    try:
        # Search related posts
        search_url = f"https://www.reddit.com/search/?q={search_keywords}"
        await main_page.goto(search_url, timeout=60000)
        await asyncio.sleep(5)
        
        # Get post links
        post_elements = await main_page.query_selector_all('a[href*="/r/"]')
        post_links = []
        seen_urls = set()
        
        for element in post_elements:
            href = await element.get_attribute('href')
            if href and '/r/' in href:
                full_url = f"https://www.reddit.com{href}" if not href.startswith('http') else href
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    post_links.append(full_url)
                    if len(post_links) >= max_posts:
                        break
        
        results["SearchedPosts"] = len(post_links)
        
        if not post_links:
            return f"No posts found related to \"{search_keywords}\""
        
        # Iterate through each post, analyze comments
        for post_url in post_links:
            try:
                comments = await _get_note_comments_structured(post_url)
                results["AnalyzedComments"] += len(comments)
                
                for comment in comments:
                    comment_content = comment.get("Content", "")
                    username = comment.get("Username", "")
                    
                    if not comment_content or len(comment_content) < 5:
                        continue
                    
                    match_result = await _analyze_comment_match(comment_content, product_description)
                    
                    if match_result["needs_product"] and match_result["match_score"] >= min_match_score:
                        results["MatchedComments"] += 1
                        reply_text = await _generate_reply_content(comment_content, product_description, username)
                        
                        results["MatchedCommentDetails"].append({
                            "Post": post_url,
                            "User": username,
                            "Comment": comment_content[:50] + "...",
                            "MatchScore": match_result["match_score"],
                            "Reply": reply_text
                        })
                        
                        try:
                            reply_result = await reply_to_comment_impl(post_url, comment_content, reply_text)
                            if "success" in reply_result.lower():
                                results["SuccessfulReplies"] += 1
                            else:
                                results["FailedReplies"].append({
                                    "User": username,
                                    "Reason": reply_result
                                })
                        except Exception as e:
                            results["FailedReplies"].append({
                                "User": username,
                                "Reason": f"Error replying: {str(e)}"
                            })
                        
                        await asyncio.sleep(5)
                
                await asyncio.sleep(3)
            except Exception as e:
                continue
        
        # Generate report
        report = f"""
Auto promotion product execution completed!

Product description: {product_description[:50]}...
Search keywords: {results['SearchKeywords']}

Execution statistics:
- Searched posts: {results['SearchedPosts']}
- Analyzed comments: {results['AnalyzedComments']}
- Matched comments: {results['MatchedComments']}
- Successful replies: {results['SuccessfulReplies']}
- Failed replies: {len(results['FailedReplies'])}
"""
        
        if results["MatchedCommentDetails"]:
            report += "\nMatched comment details:\n"
            for i, detail in enumerate(results["MatchedCommentDetails"][:10], 1):
                report += f"\n{i}. User: {detail['User']}\n"
                report += f"   Comment: {detail['Comment']}\n"
                report += f"   Match score: {detail['MatchScore']:.1f}\n"
                report += f"   Reply: {detail['Reply']}\n"
        
        if results["FailedReplies"]:
            report += "\nFailed replies:\n"
            for i, fail in enumerate(results["FailedReplies"][:5], 1):
                report += f"{i}. {fail['User']}: {fail['Reason']}\n"
        
        return report
    
    except Exception as e:
        return f"Error auto promoting product: {str(e)}"

if __name__ == "__main__":
    # Initialize and run server
    print("Starting Reddit MCP server...")
    print("Please configure this server in MCP client (e.g., Claude for Desktop)")
    mcp.run(transport='stdio')