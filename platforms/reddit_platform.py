"""
Reddit platform implementation - Self-contained Reddit-specific logic
Uses service_mcp.py only for shared utilities (browser management, LLM)
"""
from .base_platform import BasePlatform
from typing import List, Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
import asyncio
import time
import re
import random

# Import shared utilities from service_mcp
import service_mcp


class RedditPlatform(BasePlatform):
    """Self-contained Reddit platform implementation"""
    
    def __init__(self, browser_context: Optional[BrowserContext] = None, main_page: Optional[Page] = None):
        super().__init__(browser_context, main_page)
        self.is_logged_in = False
    
    def get_platform_name(self) -> str:
        return "reddit"
    
    def get_base_url(self) -> str:
        return "https://www.reddit.com"
    
    async def ensure_browser(self) -> bool:
        """Ensure browser is initialized using shared utility"""
        result = await service_mcp.ensure_browser()
        # Update our references to shared browser context and page
        self.browser_context = service_mcp.browser_context
        self.main_page = service_mcp.main_page
        # Check login status
        if not self.is_logged_in:
            if self.main_page:
                try:
                    await self.main_page.goto("https://www.reddit.com", timeout=60000)
                    await asyncio.sleep(3)
                    login_elements = await self.main_page.query_selector_all('text="Log In"')
                    self.is_logged_in = not bool(login_elements)
                except:
                    pass
        return result
    
    async def login(self) -> str:
        """Login to Reddit account"""
        await self.ensure_browser()
        
        if self.is_logged_in:
            return "Already logged in to Reddit account"
        
        if not self.main_page:
            return "Browser page not initialized, please retry"
        
        try:
            # Visit Reddit login page
            await self.main_page.goto("https://www.reddit.com", timeout=60000)
            await asyncio.sleep(3)
            
            # Find and click login button
            login_elements = await self.main_page.query_selector_all('text="Log In"')
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
                    still_login = await self.main_page.query_selector_all('text="Log In"')
                    if not still_login:
                        self.is_logged_in = True
                        await asyncio.sleep(2)  # Wait for page to load
                        return "Login successful!"
                    
                    # Continue waiting
                    await asyncio.sleep(wait_interval)
                    waited_time += wait_interval
                
                return "Login wait timeout. Please retry or login manually before using other features."
            else:
                self.is_logged_in = True
                return "Already logged in to Reddit account"
        except Exception as e:
            return f"Error during login: {str(e)}"
    
    async def _is_post_relevant(self, post_title: str, product_description: str) -> bool:
        """Use LLM to quickly check if a post title is relevant to the product
        
        Checks if the post:
        1. Is highly related to the given product
        2. Is NOT a competitive product promotion
        3. Probably requests the given product or asks if such a product exists
        
        Returns:
            True if post is relevant, False otherwise
        """
        if not product_description or not post_title:
            return True  # If no product description, include all posts
        
        try:
            prompt = f"""Analyze if this Reddit post title is relevant to our product.

Post Title: "{post_title}"
Our Product: {product_description}

Check if the Post Title satisfies all of the following conditions:
1. this post title is highly related to our product (not just tangentially related)
2. this post title is NOT promoting a competitive product
3. this post title probably requests our product or asks if a product like ours exists

Respond with ONLY "YES" if the 3 conditions above all satisfied, or "NO" otherwise.
Be strict - only say YES if it's clearly related to our product and not a competitor's promotion."""
            
            response = await service_mcp._call_llm(
                prompt=prompt,
                system_prompt="You are a lead qualification assistant. Analyze post titles to determine if they're relevant to a product.",
                max_tokens=50
            )
            
            # Check if response indicates relevance
            response_lower = response.strip().upper()
            return "YES" in response_lower or response_lower.startswith("YES")
            
        except Exception as e:
            print(f"[WARNING] LLM relevance check failed for post '{post_title}': {e}. Including post by default.")
            return True  # On error, include the post to avoid false negatives
    
    async def search_posts(self, keywords: str, limit: int = 100, product_description: Optional[str] = None) -> str:
        """Search for Reddit posts
        
        Args:
            keywords: Search keywords
            limit: Maximum number of results
            product_description: Optional product description for relevance filtering
        """
        login_status = await self.ensure_browser()
        if not login_status:
            return "Please login to Reddit account first"
        
        if not self.main_page:
            return "Browser page not initialized, please retry"
        
        try:
            search_start = time.time()
            print(f"[TIMING] Starting search stage - Searching for: {keywords}")
            
            # Stage 1: Navigate to search page
            nav_start = time.time()
            search_url = f"https://www.reddit.com/search/?q={keywords}"
            await self.main_page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
            nav_time = time.time() - nav_start
            print(f"[TIMING] Navigation to search page took: {nav_time:.2f}s")
            
            # Stage 2: Wait for search results to load
            wait_start = time.time()
            try:
                # Wait for post elements to appear
                await self.main_page.wait_for_selector('a[href*="/r/"][href*="/comments/"], a[data-testid="post-title"]', timeout=5000)
                wait_time = time.time() - wait_start
                print(f"[TIMING] Waiting for search results took: {wait_time:.2f}s")
            except:
                await asyncio.sleep(2)  # Fallback wait
                wait_time = time.time() - wait_start
                print(f"[TIMING] Waiting for search results (fallback) took: {wait_time:.2f}s")
            
            # Stage 3: Query post elements using multiple methods in parallel
            query_start = time.time()
            
            # Method 1: Try title links with /r/ and /comments/ pattern
            method1_start = time.time()
            method1_elements = []
            try:
                method1_elements = await self.main_page.query_selector_all('a[href*="/r/"][href*="/comments/"]')
                method1_time = time.time() - method1_start
                print(f"[TIMING] Method 1 (title links) query took: {method1_time:.2f}s, found {len(method1_elements)} elements")
            except Exception as e:
                method1_time = time.time() - method1_start
                print(f"[TIMING] Method 1 failed after {method1_time:.2f}s: {e}")
            
            # Method 2: Try data-testid="post-title" (new Reddit)
            method2_start = time.time()
            method2_elements = []
            try:
                method2_elements = await self.main_page.query_selector_all('a[data-testid="post-title"]')
                method2_time = time.time() - method2_start
                print(f"[TIMING] Method 2 (data-testid) query took: {method2_time:.2f}s, found {len(method2_elements)} elements")
            except Exception as e:
                method2_time = time.time() - method2_start
                print(f"[TIMING] Method 2 failed after {method2_time:.2f}s: {e}")
            
            # Method 3: Pattern matching on all links
            method3_start = time.time()
            method3_elements = []
            try:
                all_links = await self.main_page.query_selector_all('a[href*="/r/"]')
                print(f"Found {len(all_links)} links with /r/ pattern")
                
                # Filter for post links (contain /comments/)
                for link in all_links:
                    try:
                        href = await link.get_attribute('href')
                        if href and '/comments/' in href and '/r/' in href:
                            method3_elements.append(link)
                    except:
                        continue
                method3_time = time.time() - method3_start
                print(f"[TIMING] Method 3 (pattern matching) query took: {method3_time:.2f}s, found {len(method3_elements)} elements")
            except Exception as e:
                method3_time = time.time() - method3_start
                print(f"[TIMING] Method 3 failed after {method3_time:.2f}s: {e}")
            
            # Combine results from all methods, prioritizing Method 1 and 2
            post_elements = []
            seen_hrefs = set()
            
            for element in method1_elements + method2_elements:
                try:
                    href = await element.get_attribute('href')
                    if href and href not in seen_hrefs:
                        post_elements.append(element)
                        seen_hrefs.add(href)
                except:
                    continue
            
            # Add Method 3 results if needed
            for element in method3_elements:
                try:
                    href = await element.get_attribute('href')
                    if href and href not in seen_hrefs:
                        post_elements.append(element)
                        seen_hrefs.add(href)
                except:
                    continue
            
            query_time = time.time() - query_start
            print(f"[TIMING] Total query time (all methods) took: {query_time:.2f}s, found {len(post_elements)} unique posts")
            
            # Stage 4: Extract href and title from post elements in parallel
            extract_start = time.time()
            
            async def extract_post_info(element):
                """Extract href and title from a post element"""
                try:
                    href = await element.get_attribute('href')
                    title = await element.text_content()
                    return href, title
                except:
                    return None, None
            
            # Extract in parallel
            extract_tasks = [extract_post_info(element) for element in post_elements[:limit]]
            extract_results = await asyncio.gather(*extract_tasks, return_exceptions=True)
            
            # Stage 5: Filter posts by relevance using LLM (if product_description provided)
            filter_start = time.time()
            filtered_count = 0
            
            # First, collect all valid posts with normalized URLs
            candidate_posts = []
            for result in extract_results:
                if isinstance(result, Exception):
                    continue
                href, title = result
                if href and title:
                    # Normalize URL
                    if href and '/r/' in href and '/comments/' in href:
                        if not href.startswith('http'):
                            full_url = f"https://www.reddit.com{href}"
                        else:
                            full_url = href
                        candidate_posts.append({"href": full_url, "title": title.strip()})
            
            # If product_description is provided, filter posts in parallel using LLM
            if product_description and candidate_posts:
                async def check_relevance(post):
                    """Check if a post is relevant"""
                    is_relevant = await self._is_post_relevant(post['title'], product_description)
                    return post if is_relevant else None
                
                # Check relevance in parallel
                relevance_tasks = [check_relevance(post) for post in candidate_posts]
                relevance_results = await asyncio.gather(*relevance_tasks, return_exceptions=True)
                
                # Collect only relevant posts
                posts = []
                for result in relevance_results:
                    if isinstance(result, Exception):
                        continue
                    if result is not None:  # Post is relevant
                        posts.append(result)
                    else:  # Post was filtered out
                        filtered_count += 1
            else:
                # No filtering, include all candidate posts
                posts = candidate_posts
            
            filter_time = time.time() - filter_start
            if product_description and filtered_count > 0:
                print(f"[TIMING] LLM filtering took: {filter_time:.2f}s, filtered {filtered_count} posts, kept {len(posts)} posts")
            
            extract_time = time.time() - extract_start
            print(f"[TIMING] Extracting {len(post_elements[:limit])} post info in parallel took: {extract_time:.2f}s")
            
            # Limit results
            posts = posts[:limit]
            
            total_time = time.time() - search_start
            print(f"[TIMING] Total search stage took: {total_time:.2f}s, found {len(posts)} posts")
            
            # Format results
            if not posts:
                return "No posts found matching the search keywords"
            
            result = "Search results:\n\n"
            for i, post in enumerate(posts, 1):
                result += f"{i}. {post['title']}\n"
                result += f" Link: {post['href']}\n\n"
            
            return result
        
        except Exception as e:
            return f"Error searching posts: {str(e)}"
    
    async def get_post_content(self, url: str) -> str:
        """Get Reddit post content"""
        login_status = await self.ensure_browser()
        if not login_status:
            return "Please login to Reddit account first"
        
        if not self.main_page:
            return "Browser page not initialized, please retry"
        
        try:
            # Visit post link
            await self.main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # Wait for post content to appear instead of fixed sleep
            try:
                await self.main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
            except:
                await asyncio.sleep(1)  # Minimal fallback
            
            # Get post content
            post_content = {}
            
            # Get post title
            try:
                title_element = await self.main_page.query_selector('text="edited"')
                if title_element:
                    title = await title_element.evaluate('(el) => el.previousElementSibling ? el.previousElementSibling.textContent : ""')
                    post_content["Title"] = title.strip() if title else "Unknown title"
                else:
                    post_content["Title"] = "Unknown title"
            except Exception as e:
                post_content["Title"] = "Unknown title"
            
            # Get author
            try:
                author_element = await self.main_page.query_selector('a[href*="/user/profile/"]')
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
                    time_element = await self.main_page.query_selector(selector)
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
                    content_element = await self.main_page.query_selector(selector)
                    if content_element:
                        content_text = await content_element.text_content()
                        if content_text and len(content_text.strip()) > 10:
                            post_content["Content"] = content_text.strip()
                            break
                
                # Use JavaScript to extract main text content
                if post_content["Content"] == "Failed to get content":
                    content_text = await self.main_page.evaluate('''
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
    
    async def get_post_comments(self, url: str) -> List[Dict[str, Any]]:
        """Get Reddit post comments (returns structured data)"""
        login_status = await self.ensure_browser()
        if not login_status:
            return []
        
        if not self.main_page:
            return []
        
        try:
            comment_start_time = time.time()
            print(f"[TIMING] Starting comment extraction stage - Getting comments from URL: {url}")
            
            # Stage 1: Navigate to post page
            nav_start = time.time()
            await self.main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
            nav_time = time.time() - nav_start
            print(f"[TIMING] Navigation to post page took: {nav_time:.2f}s")
            
            # Wait for page content to load - use wait_for_selector instead of fixed sleep
            wait_start = time.time()
            try:
                # Wait for post title or content to appear (max 3 seconds)
                await self.main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
                wait_time = time.time() - wait_start
                print(f"[TIMING] Waiting for post content took: {wait_time:.2f}s")
            except:
                # Fallback: minimal wait
                await asyncio.sleep(0.5)
                wait_time = time.time() - wait_start
                print(f"[TIMING] Waiting for post content (fallback) took: {wait_time:.2f}s")
            
            comments = []
            
            # Method 1: Try modern Reddit selectors (shreddit-comment elements)
            method1_start = time.time()
            try:
                # Wait for comments to load
                comment_wait_start = time.time()
                try:
                    await self.main_page.wait_for_selector('shreddit-comment, .Comment, [class*="Comment"]', timeout=5000)
                    comment_wait_time = time.time() - comment_wait_start
                    print(f"[TIMING] Waiting for comments to load took: {comment_wait_time:.2f}s")
                except:
                    await asyncio.sleep(2)  # Fallback wait
                    comment_wait_time = time.time() - comment_wait_start
                    print(f"[TIMING] Waiting for comments (fallback) took: {comment_wait_time:.2f}s")
                
                # Query comment elements
                query_start = time.time()
                comment_elements = await self.main_page.query_selector_all('shreddit-comment')
                query_time = time.time() - query_start
                print(f"[TIMING] Querying shreddit-comment elements took: {query_time:.2f}s, found {len(comment_elements)} elements")
                
                if len(comment_elements) == 0:
                    # Try alternative selectors
                    comment_elements = await self.main_page.query_selector_all('.Comment, [class*="Comment"], [data-testid="comment"]')
                    print(f"[TIMING] Querying alternative comment selectors found {len(comment_elements)} elements")
                
                # Process each comment element in parallel
                process_start = time.time()
                
                async def process_comment_element(element):
                    """Process a single comment element"""
                    try:
                        username = "[deleted]"
                        try:
                            # Try to get username from shadow DOM or regular DOM
                            username_el = await element.query_selector('a[href*="/user/"], a[href*="/u/"], [data-testid="comment_author_link"]')
                            if username_el:
                                username_text = await username_el.text_content()
                                if username_text:
                                    username = username_text.strip()
                            else:
                                # Try JavaScript evaluation for shadow DOM
                                username_text = await element.evaluate('''
                                    (el) => {
                                        if (el.shadowRoot) {
                                            const authorLink = el.shadowRoot.querySelector('a[href*="/user/"], a[href*="/u/"]');
                                            if (authorLink) return authorLink.textContent.trim();
                                        }
                                        const authorLink = el.querySelector('a[href*="/user/"], a[href*="/u/"]');
                                        if (authorLink) return authorLink.textContent.trim();
                                        return null;
                                    }
                                ''')
                                if username_text:
                                    username = username_text
                        except:
                            pass
                        
                        content = ""
                        try:
                            # Try to get content from shadow DOM
                            content_text = await element.evaluate('''
                                (el) => {
                                    if (el.shadowRoot) {
                                        const contentEl = el.shadowRoot.querySelector('[data-testid="comment"], .md, p, div[class*="comment"]');
                                        if (contentEl) return contentEl.textContent.trim();
                                    }
                                    const contentEl = el.querySelector('[data-testid="comment"], .md, p, div[class*="comment"]');
                                    if (contentEl) return contentEl.textContent.trim();
                                    return el.textContent.trim();
                                }
                            ''')
                            if content_text and len(content_text.strip()) > 10:
                                content = content_text.strip()
                        except:
                            # Fallback to element text
                            try:
                                full_text = await element.text_content()
                                if full_text and len(full_text.strip()) > 10:
                                    content = full_text.strip()
                            except:
                                pass
                        
                        time_location = "Unknown time"
                        try:
                            time_el = await element.query_selector('time, [data-testid="comment_timestamp"]')
                            if time_el:
                                time_text = await time_el.get_attribute('title') or await time_el.get_attribute('datetime') or await time_el.text_content()
                                if time_text:
                                    time_location = time_text.strip()
                            else:
                                # Try shadow DOM
                                time_text = await element.evaluate('''
                                    (el) => {
                                        if (el.shadowRoot) {
                                            const timeEl = el.shadowRoot.querySelector('time');
                                            if (timeEl) return timeEl.getAttribute('title') || timeEl.textContent.trim();
                                        }
                                        return null;
                                    }
                                ''')
                                if time_text:
                                    time_location = time_text
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
                    comment_elements = await self.main_page.query_selector_all('.comment, .Comment, [class*="comment"]')
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
                    print(f"[TIMING] Method 2 failed after {method2_time:.2f}s: {e}")
            
            total_time = time.time() - comment_start_time
            print(f"[TIMING] Total comment extraction stage took: {total_time:.2f}s, extracted {len(comments)} comments")
            
            return comments
        
        except Exception as e:
            print(f"Error getting post comments: {str(e)}")
            return []
    
    async def post_comment(self, url: str, comment_text: str, comment_type: str = "lead_gen") -> str:
        """Post a comment on Reddit post"""
        login_status = await self.ensure_browser()
        if not login_status:
            return "Please login to Reddit account first to post comments"
        
        if not self.main_page:
            return "Browser page not initialized, please retry"
        
        try:
            # Visit post link
            await self.main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # Wait for post content to appear instead of fixed sleep
            try:
                await self.main_page.wait_for_selector('h1[data-testid="post-title"], h1, [data-testid="post-title"]', timeout=3000)
            except:
                await asyncio.sleep(1)  # Minimal fallback
            
            # If comment_text is provided, use it directly
            if comment_text and comment_text.strip():
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
                            title_element = await self.main_page.query_selector(selector)
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
                            author_element = await self.main_page.query_selector(selector)
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
                            content_element = await self.main_page.query_selector(selector)
                            if content_element:
                                content_text = await content_element.text_content()
                                if content_text and len(content_text.strip()) > 10:
                                    post_content["Content"] = content_text.strip()
                                    break
                        except:
                            continue
                    
                    # Use JavaScript to extract main text content
                    if post_content["Content"] == "Failed to get content":
                        content_text = await self.main_page.evaluate('''
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
                final_comment_text = await self._generate_smart_comment(post_content, comment_type)
            
            # Use shared utility to type and submit comment
            input_selectors = [
                'paragraph:has-text("Add a comment...")',
                'text="Add a comment..."',
                'text="What are your thoughts?"',
                'div[contenteditable="true"]',
                'textarea[placeholder*="comment"]'
            ]
            
            submit_selectors = [
                'button:has-text("Comment")',
                'button:has-text("Post")',
                'button[type="submit"]',
                'button[data-testid="submit-button"]'
            ]
            
            scroll_selector = 'text="comments"'
            
            success, message = await service_mcp.type_and_submit_comment(
                page=self.main_page,
                comment_text=final_comment_text,
                input_selectors=input_selectors,
                submit_selectors=submit_selectors,
                scroll_to_selector=scroll_selector
            )
            
            return message
        
        except Exception as e:
            return f"Error posting comment: {str(e)}"
    
    async def reply_to_comment(self, url: str, comment_content: str, reply_text: str) -> str:
        """Reply to a specific Reddit comment"""
        login_status = await self.ensure_browser()
        if not login_status:
            return "Please login to Reddit account first to reply to comments"
        
        if not self.main_page:
            return "Browser page not initialized, please retry"
        
        try:
            # Visit post link
            await self.main_page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Find comment containing the specified content
            comment_found = False
            
            # Use shared utility to find and reply to comment
            comment_container_selector = 'shreddit-comment, .Comment, [class*="comment"]'
            reply_button_selectors = [
                'button:has-text("Reply")',
                'button[aria-label*="reply"]',
                'text="Reply"'
            ]
            reply_input_selectors = [
                'div[contenteditable="true"]',
                'textarea[placeholder*="comment"]',
                'text="Add a comment..."',
            ]
            reply_submit_selectors = [
                'button:has-text("Comment")',
                'button:has-text("Reply")',
                'button[type="submit"]',
            ]
            
            success, message = await service_mcp.find_and_reply_to_comment(
                page=self.main_page,
                comment_content=comment_content,
                reply_text=reply_text,
                comment_container_selector=comment_container_selector,
                reply_button_selectors=reply_button_selectors,
                reply_input_selectors=reply_input_selectors,
                reply_submit_selectors=reply_submit_selectors
            )
            
            return message
        
        except Exception as e:
            return f"Error replying to comment: {str(e)}"
    
    def get_search_url(self, keywords: str) -> str:
        """Get Reddit search URL for given keywords"""
        return f"{self.get_base_url()}/search/?q={keywords}"
    
    # Reddit-specific helper methods
    
    async def _generate_smart_comment(self, post_content: dict, comment_type: str) -> str:
        """Generate smart comment based on post content and comment type (uses shared utility)"""
        title = post_content.get("Title", "")
        content = post_content.get("Content", "")
        author = post_content.get("Author", "")
        
        # Use shared utility to detect domain
        detected_domains = service_mcp.detect_content_domain(title, content)
        domain = detected_domains[0] if detected_domains else "lifestyle"
        
        # Use shared utility to generate comment template
        return service_mcp.generate_comment_template(
            comment_type=comment_type,
            domain=domain,
            author=author,
            title=title,
            platform_name="Reddit"
        )
    
    async def generate_search_keywords(self, product_description: str) -> str:
        """Generate search keywords for Reddit using LLM (via shared utility)"""
        system_prompt = """You are a professional search keyword generation assistant. Your task is to generate keywords suitable for searching on Reddit platform based on product description.

Requirements:
1. Extract core features and uses of the product
2. Generate 2-5 most relevant search keywords
3. Keywords should match Reddit users' search habits
4. Keywords should be concise and accurate, avoid being too long
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
            # Call shared LLM utility
            keywords = await service_mcp._call_llm(user_prompt, system_prompt, max_tokens=50)
            
            if not keywords:
                # LLM call failed, use shared fallback utility
                return service_mcp.extract_keywords_fallback(product_description)
            
            # Use shared utility to clean keywords
            keywords = service_mcp.clean_keywords(keywords)
            
            # Ensure keywords are not empty
            if not keywords or len(keywords) < 2:
                return service_mcp.extract_keywords_fallback(product_description)
            
            return keywords
        
        except Exception as e:
            print(f"Error generating search keywords with LLM: {str(e)}")
            # On error, use shared fallback utility
            return service_mcp.extract_keywords_fallback(product_description)