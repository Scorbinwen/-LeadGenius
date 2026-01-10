"""
Shared utilities for browser management and LLM calls
All platform-specific code has been moved to platform classes (e.g., RedditPlatform)
"""
from typing import Any, List, Dict, Optional, Tuple
import sys
import platform as platform_module
import asyncio
import os
import re
import random
from playwright.async_api import async_playwright, Page, Locator
from fastmcp import FastMCP
from dotenv import load_dotenv

# Fix for Windows asyncio event loop policy
# Windows default ProactorEventLoop doesn't support subprocess operations properly
if platform_module.system() == "Windows":
    if sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    else:
        # For Python < 3.8, use SelectorEventLoop
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)

# Load environment variables
load_dotenv()

# Initialize FastMCP server (for backward compatibility with MCP clients)
mcp = FastMCP("reddit_scraper")

# Global variables for shared browser state
BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Ensure directories exist
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Store browser context to share between different platforms and methods
browser_context = None
main_page = None
is_logged_in = False  # Note: This is platform-specific but kept here for backward compatibility
playwright_instance = None
current_loop_id = None  # Store event loop ID

# LLM Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "openai", "gemini", "anthropic" or "ollama"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://10.10.10.217:11434/v1")  # Ollama server address (needs /v1 path)
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen2")  # Default model name

async def _call_llm(prompt: str, system_prompt: str = "", max_tokens: int = 500) -> str:
    """Call LLM API (shared utility for all platforms)
    
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
    """Ensure browser is started (shared utility for all platforms)
    
    Note: This function manages the shared browser instance used by all platforms.
    Individual platforms should handle their own login logic in their platform classes.
    
    Returns:
        bool: True if browser is ready, False if login is needed
    """
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
    
    # Note: Login checking is platform-specific and should be handled by platform classes
    # This function just ensures the browser is ready
    
    return True

# ============================================================================
# Shared Playwright Helper Functions (used by all platforms)
# ============================================================================

async def find_element_by_selectors(page: Page, selectors: List[str], timeout: int = 3000) -> Optional[Any]:
    """Find an element using multiple selectors (shared utility)
    
    Args:
        page: Playwright page object
        selectors: List of CSS selectors to try
        timeout: Timeout in milliseconds
    
    Returns:
        Element if found, None otherwise
    """
    for selector in selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                is_visible = await element.is_visible()
                if is_visible:
                    return element
        except Exception:
            continue
    return None

async def find_clickable_element(page: Page, selectors: List[str], text_contains: Optional[str] = None) -> Optional[Any]:
    """Find a clickable element (button/link) using multiple selectors (shared utility)
    
    Args:
        page: Playwright page object
        selectors: List of CSS selectors to try
        text_contains: Optional text that element should contain
    
    Returns:
        Element if found, None otherwise
    """
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                if text_contains:
                    text = await element.text_content()
                    if text_contains.lower() in (text or "").lower():
                        if await element.is_visible():
                            return element
                else:
                    if await element.is_visible():
                        return element
        except Exception:
            continue
    return None

async def type_and_submit_comment(
    page: Page,
    comment_text: str,
    input_selectors: List[str],
    submit_selectors: List[str],
    scroll_to_selector: Optional[str] = None
) -> Tuple[bool, str]:
    """Generic function to type and submit a comment (shared utility)
    
    Args:
        page: Playwright page object
        comment_text: Text to post
        input_selectors: List of selectors to find comment input box
        submit_selectors: List of selectors to find submit button
        scroll_to_selector: Optional selector to scroll to before typing
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Scroll to comment area if specified
        if scroll_to_selector:
            try:
                scroll_element = await page.query_selector(scroll_to_selector)
                if scroll_element:
                    await scroll_element.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
            except Exception:
                pass
        
        # Find comment input box
        comment_input = await find_element_by_selectors(page, input_selectors, timeout=3000)
        
        if not comment_input:
            # Try JavaScript-based finding as fallback
            comment_input = await page.evaluate('''
                () => {
                    const elements = Array.from(document.querySelectorAll('*'))
                        .filter(el => el.textContent && (
                            el.textContent.includes('Add a comment') ||
                            el.textContent.includes('What are your thoughts') ||
                            el.textContent.includes('Write a comment')
                        ));
                    if (elements.length > 0) return elements[0];
                    const editableDivs = Array.from(document.querySelectorAll('div[contenteditable="true"], textarea[placeholder*="comment"]'));
                    if (editableDivs.length > 0) return editableDivs[0];
                    return null;
                }
            ''')
            
            if comment_input:
                # Convert handle to element
                all_elements = await page.query_selector_all('*')
                if all_elements:
                    comment_input = all_elements[-1]  # Fallback
        
        if not comment_input:
            return False, "Unable to find comment input box"
        
        # Click input box
        await comment_input.click()
        
        # Wait for input to be focused
        try:
            await comment_input.wait_for(state="visible", timeout=500)
        except:
            await asyncio.sleep(0.2)
        
        # Type comment content
        await page.keyboard.type(comment_text, delay=30)
        await asyncio.sleep(0.3)
        
        # Find and click submit button
        submit_button = await find_clickable_element(page, submit_selectors)
        
        if submit_button:
            await submit_button.click()
        else:
            # Try using Enter key
            await page.keyboard.press('Enter')
        
        # Wait for confirmation
        try:
            await page.wait_for_selector(input_selectors[0] if input_selectors else 'text="Add a comment..."', timeout=3000, state="visible")
        except:
            await asyncio.sleep(1)
        
        return True, f"Successfully posted comment: {comment_text[:50]}..."
    
    except Exception as e:
        return False, f"Error posting comment: {str(e)}"

async def find_and_reply_to_comment(
    page: Page,
    comment_content: str,
    reply_text: str,
    comment_container_selector: str,
    reply_button_selectors: List[str],
    reply_input_selectors: List[str],
    reply_submit_selectors: List[str]
) -> Tuple[bool, str]:
    """Generic function to find a comment and reply to it (shared utility)
    
    Args:
        page: Playwright page object
        comment_content: Content of comment to find
        reply_text: Text to reply with
        comment_container_selector: Selector for comment containers
        reply_button_selectors: Selectors to find reply button
        reply_input_selectors: Selectors to find reply input box
        reply_submit_selectors: Selectors to find submit button
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Find all comment elements
        comment_elements = await page.query_selector_all(comment_container_selector)
        
        for element in comment_elements:
            try:
                element_text = await element.text_content()
                
                if comment_content.lower() in (element_text or "").lower():
                    # Found matching comment, look for reply button
                    reply_button = None
                    
                    for selector in reply_button_selectors:
                        try:
                            reply_el = await element.query_selector(selector)
                            if reply_el and await reply_el.is_visible():
                                reply_button = reply_el
                                break
                        except Exception:
                            continue
                    
                    if not reply_button:
                        return False, "Found comment but unable to find reply button"
                    
                    # Click reply button
                    await reply_button.click()
                    await asyncio.sleep(0.5)
                    
                    # Find reply input box
                    reply_input = await find_element_by_selectors(page, reply_input_selectors, timeout=2000)
                    
                    if not reply_input:
                        return False, "Found comment but unable to locate reply input box"
                    
                    # Click input box and type
                    await reply_input.click()
                    try:
                        await reply_input.wait_for(state="visible", timeout=300)
                    except:
                        await asyncio.sleep(0.1)
                    
                    await page.keyboard.type(reply_text, delay=30)
                    await asyncio.sleep(0.3)
                    
                    # Submit reply
                    submit_button = await find_clickable_element(page, reply_submit_selectors)
                    
                    if submit_button:
                        await submit_button.click()
                    else:
                        await page.keyboard.press('Enter')
                    
                    # Wait for confirmation
                    try:
                        await page.wait_for_selector(reply_button_selectors[0] if reply_button_selectors else 'button:has-text("Reply")', timeout=2000, state="hidden")
                    except:
                        await asyncio.sleep(1)
                    
                    return True, f"Successfully replied to comment: {reply_text}"
            
            except Exception:
                continue
        
        return False, f"Comment containing \"{comment_content[:20]}...\" not found, unable to reply"
    
    except Exception as e:
        return False, f"Error replying to comment: {str(e)}"

# ============================================================================
# Shared Text Processing Utilities
# ============================================================================

def clean_keywords(text: str) -> str:
    """Clean and normalize keywords (shared utility)
    
    Args:
        text: Raw keyword text
    
    Returns:
        Cleaned keywords
    """
    # Remove quotes
    text = text.strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1]
    
    # Replace commas with spaces
    text = text.replace(",", " ").replace("，", " ")
    
    # Clean extra spaces
    text = " ".join(text.split())
    
    return text.strip()

def extract_keywords_fallback(text: str, min_length: int = 2) -> str:
    """Extract keywords using simple fallback method (shared utility)
    
    Args:
        text: Text to extract keywords from
        min_length: Minimum keyword length
    
    Returns:
        Space-separated keywords
    """
    # Extract words
    words = re.findall(r'\w+', text.lower())
    
    # Filter out common stop words
    stop_words = {
        "product", "description", "suitable", "can", "able", "has", "provide", "include", "contain",
        "the", "a", "an", "and", "or", "but", "for", "with", "from", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having"
    }
    
    keywords = [word for word in words if word not in stop_words and len(word) >= min_length]
    
    # Take first 3-5 keywords
    keywords = keywords[:5]
    
    if keywords:
        return " ".join(keywords)
    else:
        # Fallback: return first 20 characters
        return text[:20].strip()

# ============================================================================
# Shared Comment Generation Utilities (platform-agnostic)
# ============================================================================

def detect_content_domain(title: str, content: str) -> List[str]:
    """Detect content domain/category from title and content (shared utility)
    
    Args:
        title: Post title
        content: Post content
    
    Returns:
        List of detected domains
    """
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
    
    detected_domains = []
    text_lower = (title + " " + content).lower()
    
    for domain, keywords in domain_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            detected_domains.append(domain)
    
    return detected_domains if detected_domains else ["lifestyle"]

def generate_comment_template(
    comment_type: str,
    domain: str,
    author: str = "",
    title: str = "",
    platform_name: str = "social media"
) -> str:
    """Generate comment using templates (shared utility, platform-agnostic)
    
    Args:
        comment_type: Type of comment ("lead_gen", "like", "consult", "professional")
        domain: Content domain (e.g., "beauty", "tech", "fitness")
        author: Post author name
        title: Post title
        platform_name: Name of the platform (for customization)
    
    Returns:
        Generated comment text
    """
    templates = {
        "lead_gen": [
            f"This {domain} share is great! I'm also researching related content, feel free to DM me~",
            f"Thanks for sharing, {author}'s insights are unique! I've also compiled some related materials, interested to chat?" if author else "Thanks for sharing! I've also compiled some related materials, interested to chat?",
            f"Your share is very insightful! I've written similar content, feel free to reach out",
            f"Really like your sharing style! I also do {domain} related content, we can follow each other",
            f"Totally relate! I've encountered similar situations, DM me if you want to know more",
            f"This post has so much info! Saved it, we can discuss if you have questions~"
        ],
        "like": [
            f"Awesome! {author}'s shares are always so practical" if author else "Awesome! This is so practical",
            f"Every time I see {author}'s shares I learn something, keep it up!" if author else "I learn something new every time, keep it up!",
            f"This content is super detailed, learned a lot, thanks for sharing!",
            f"Love this in-depth share, much more meaningful than typical {domain} posts",
            f"Saved and upvoted, very valuable reference",
            f"This kind of high-quality content is rare, thanks for sharing"
        ],
        "consult": [
            f"Hey OP, any beginner tips for {domain}?",
            f"This {domain} technique looks practical, is it suitable for beginners?",
            f"OP's shared experience is so valuable, can you elaborate on how you got started?",
            f"Very inspiring, would like to ask {author}, how did you reach such a professional level?" if author else "Very inspiring! How did you reach such a professional level?",
            f"Very interested in this field, any recommended learning resources to share?",
            f"OP's insights are unique, could you share your learning path?"
        ],
        "professional": [
            f"As a {domain} practitioner, I agree with OP's points, especially about {title[:10] if title else 'this'}",
            f"From a professional perspective, this share covers key points, I'd like to add...",
            f"This analysis is spot on, I've found similar patterns in practice, totally agree",
            f"Very professional share! I've been in related work for years, these methods really work",
            f"The depth of this content is impressive, shows OP's professional expertise",
            f"From a technical perspective, the methods OP shared are very feasible, worth trying"
        ]
    }
    
    if comment_type not in templates:
        comment_type = "lead_gen"
    
    selected_template = random.choice(templates[comment_type])
    
    # Add domain-specific terms for professional comments
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
        
        if domain in domain_terms and random.random() > 0.5:
            selected_term = random.choice(domain_terms[domain])
            selected_template += f", especially insights on {selected_term} are unique"
    
    # Add DM-attracting endings
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

# Export shared utilities
__all__ = [
    'ensure_browser',
    '_call_llm',
    'browser_context',
    'main_page',
    'is_logged_in',  # For backward compatibility
    'BROWSER_DATA_DIR',
    'DATA_DIR',
    # Playwright helpers
    'find_element_by_selectors',
    'find_clickable_element',
    'type_and_submit_comment',
    'find_and_reply_to_comment',
    # Text processing
    'clean_keywords',
    'extract_keywords_fallback',
    # Comment generation
    'detect_content_domain',
    'generate_comment_template',
]

if __name__ == "__main__":
    # Initialize and run MCP server (for backward compatibility)
    print("Starting MCP server...")
    print("Note: Platform-specific functions have been moved to platform classes.")
    print("Please use RedditPlatform, TwitterPlatform, etc. for platform-specific operations.")
    mcp.run(transport='stdio')
