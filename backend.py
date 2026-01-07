"""
FastAPI Backend Server for LeadGen AI
Wraps service_mcp.py functions as REST API endpoints (Reddit integration)
"""
# CRITICAL: Set Windows event loop policy BEFORE any other imports
# This must be the very first thing we do
import sys
import platform

if platform.system() == "Windows":
    import asyncio
    # Set policy before ANY event loop is created or any asyncio operations
    if sys.version_info >= (3, 8):
        # Force set the policy - this must happen before uvicorn or any async code runs
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        print("✓ backend.py: Windows event loop policy set to WindowsSelectorEventLoopPolicy")
    else:
        # For Python < 3.8, use SelectorEventLoop
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        print("✓ backend.py: Windows event loop set to SelectorEventLoop")

# Now import asyncio normally (it's already imported above on Windows, but that's OK)
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import uvicorn
import os
import time
# Import functions from service_mcp
# Note: We import both MCP tools and _impl versions for flexibility
try:
    import service_mcp
    # Import functions explicitly
    login_impl = getattr(service_mcp, 'login_impl', None)
    search_notes_impl = getattr(service_mcp, 'search_notes_impl', None)
    get_note_content_impl = getattr(service_mcp, 'get_note_content_impl', None)
    # Use _impl version to avoid FunctionTool wrapper from @mcp.tool() decorator
    get_note_comments_impl = getattr(service_mcp, 'get_note_comments_impl', None)
    post_smart_comment = getattr(service_mcp, 'post_smart_comment', None)
    reply_to_comment = getattr(service_mcp, 'reply_to_comment', None)
    # Use _impl version to avoid FunctionTool wrapper from @mcp.tool() decorator
    generate_search_keywords_impl = getattr(service_mcp, 'generate_search_keywords_impl', None)
    post_smart_comment_impl = getattr(service_mcp, 'post_smart_comment_impl', None)
    auto_promote_product = getattr(service_mcp, 'auto_promote_product', None)
    ensure_browser = getattr(service_mcp, 'ensure_browser', None)
    
    # Verify critical imports
    if login_impl is None:
        raise ImportError("login_impl not found in service_mcp module. Please check service_mcp.py")
    if not callable(login_impl):
        raise ImportError(f"login_impl is not callable. Type: {type(login_impl)}. Value: {login_impl}")
    
    # Print confirmation
    print(f"✓ Successfully imported login_impl: {type(login_impl)}, callable: {callable(login_impl)}")
        
except ImportError as e:
    print(f"Error: Could not import from service_mcp: {e}")
    print("Make sure service_mcp.py is in the same directory as backend.py")
    raise
except Exception as e:
    print(f"Error importing from service_mcp: {e}")
    import traceback
    traceback.print_exc()
    raise

# Use lifespan context manager (replaces deprecated on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    if platform.system() == "Windows":
        try:
            loop = asyncio.get_running_loop()
            loop_type = type(loop).__name__
            print(f"Current event loop type: {loop_type}")
            
            # Check if it's a ProactorEventLoop (which doesn't support subprocess)
            if "Proactor" in loop_type:
                print("⚠️  WARNING: Current event loop is ProactorEventLoop!")
                print("⚠️  This will cause issues with Playwright subprocess operations.")
                print("⚠️  The event loop policy should be set before uvicorn starts.")
            elif "Selector" in loop_type:
                print("✓ Event loop is SelectorEventLoop - Playwright should work correctly")
            else:
                print(f"ℹ️  Event loop type: {loop_type}")
        except Exception as e:
            print(f"Could not check event loop: {e}")
    
    yield
    
    # Shutdown (cleanup if needed)
    pass

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="LeadGen AI API",
    description="AI-Powered Lead Generation Backend API",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class LoginResponse(BaseModel):
    success: bool
    message: str

class SearchNotesRequest(BaseModel):
    keywords: str = Field(..., description="Search keywords")
    limit: int = Field(100, ge=1, le=500, description="Maximum number of results")

class SearchNotesResponse(BaseModel):
    success: bool
    results: List[Dict[str, str]]
    message: str

class GetNoteContentRequest(BaseModel):
    url: str = Field(..., description="Note URL")

class GetNoteContentResponse(BaseModel):
    success: bool
    content: str
    message: str

class GetCommentsRequest(BaseModel):
    url: str = Field(..., description="Note URL")

class GetCommentsResponse(BaseModel):
    success: bool
    comments: List[Dict[str, str]]
    message: str

class PostCommentRequest(BaseModel):
    url: str = Field(..., description="Note URL")
    comment_type: str = Field("lead_gen", description="Comment type: lead_gen, like, consult, professional")
    comment_text: Optional[str] = Field(None, description="Optional: Pre-generated comment text to post directly without regenerating")

class PostCommentResponse(BaseModel):
    success: bool
    message: str

class ReplyCommentRequest(BaseModel):
    url: str = Field(..., description="Note URL")
    comment_content: str = Field(..., description="Comment content to reply to")
    reply_text: str = Field(..., description="Reply text")

class ReplyCommentResponse(BaseModel):
    success: bool
    message: str

class GenerateKeywordsRequest(BaseModel):
    product_description: str = Field(..., description="Product description")

class GenerateKeywordsResponse(BaseModel):
    success: bool
    keywords: str
    message: str

class AutoPromoteRequest(BaseModel):
    product_description: str = Field(..., description="Product description")
    search_keywords: Optional[str] = Field(None, description="Search keywords (auto-generated if not provided)")
    max_posts: int = Field(5, ge=1, le=20, description="Maximum number of posts to process")
    min_match_score: float = Field(40.0, ge=0, le=100, description="Minimum match score")

class AutoPromoteResponse(BaseModel):
    success: bool
    report: str
    message: str

class HealthResponse(BaseModel):
    status: str
    message: str

class AnalyzeProductRequest(BaseModel):
    product_description: str = Field(..., description="Product description")
    website_url: Optional[str] = Field(None, description="Website URL (optional)")

class AnalyzeProductResponse(BaseModel):
    success: bool
    leads: List[Dict[str, Any]]
    message: str

# API Endpoints

@app.get("/")
async def root():
    """Serve the main website"""
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        return {
            "status": "healthy",
            "message": "LeadGen AI API is running. index.html not found."
        }

@app.get("/dashboard.html")
async def dashboard():
    """Serve the dashboard page"""
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    else:
        raise HTTPException(status_code=404, detail="Dashboard page not found")

@app.get("/smart-comment.html")
async def smart_comment_page():
    """Serve the smart comment page"""
    smart_comment_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smart-comment.html")
    if os.path.exists(smart_comment_path):
        return FileResponse(smart_comment_path)
    else:
        raise HTTPException(status_code=404, detail="Smart comment page not found")

# Serve static files (CSS, JS) - must be after API routes
@app.get("/styles.css")
async def serve_css():
    """Serve CSS file"""
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "styles.css")
    if os.path.exists(css_path):
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS file not found")

@app.get("/script.js")
async def serve_script():
    """Serve JavaScript file"""
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JavaScript file not found")

@app.get("/api.js")
async def serve_api_js():
    """Serve API JavaScript file"""
    api_js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api.js")
    if os.path.exists(api_js_path):
        return FileResponse(api_js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="API JavaScript file not found")

@app.get("/dashboard.js")
async def serve_dashboard_js():
    """Serve dashboard JavaScript file"""
    dashboard_js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.js")
    if os.path.exists(dashboard_js_path):
        return FileResponse(dashboard_js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Dashboard JavaScript file not found")

@app.get("/analyze.html")
async def analyze_page():
    """Serve the analyze page"""
    analyze_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze.html")
    if os.path.exists(analyze_path):
        return FileResponse(analyze_path)
    else:
        raise HTTPException(status_code=404, detail="Analyze page not found")

@app.get("/analyze.js")
async def serve_analyze_js():
    """Serve analyze JavaScript file"""
    analyze_js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze.js")
    if os.path.exists(analyze_js_path):
        return FileResponse(analyze_js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Analyze JavaScript file not found")

@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Health check endpoint - checks API status without initializing browser"""
    try:
        # Simple API health check - don't initialize browser unless needed
        # Just verify the API is responding
        return {
            "status": "healthy",
            "message": "API is running and ready. Browser will be initialized when needed."
        }
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error"
        return {
            "status": "error",
            "message": f"API health check failed: {error_msg}"
        }

@app.get("/api/debug-imports")
async def debug_imports():
    """Debug endpoint to check what functions are imported"""
    try:
        import service_mcp
        return {
            "login_impl": {
                "exists": hasattr(service_mcp, 'login_impl'),
                "type": str(type(getattr(service_mcp, 'login_impl', None))),
                "callable": callable(getattr(service_mcp, 'login_impl', None))
            },
            "module_attrs": [attr for attr in dir(service_mcp) if not attr.startswith('_')][:20],
            "backend_login_impl": {
                "exists": login_impl is not None,
                "type": str(type(login_impl)),
                "callable": callable(login_impl) if login_impl is not None else False
            }
        }
    except Exception as e:
        return {"error": str(e), "traceback": str(__import__('traceback').format_exc())}

@app.get("/api/browser-status", response_model=HealthResponse)
async def browser_status():
    """Check browser initialization status"""
    try:
        # Try to check browser status without forcing initialization
        from service_mcp import browser_context, is_logged_in
        
        if browser_context is None:
            return {
                "status": "not_initialized",
                "message": "Browser not initialized yet. It will be initialized when you use features that require it."
            }
        
        # Try to check if browser is still alive
        try:
            pages = browser_context.pages
            return {
                "status": "ready",
                "message": f"Browser is ready. Logged in: {is_logged_in}. Pages: {len(pages)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Browser context exists but may be closed: {str(e)}"
            }
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error"
        return {
            "status": "error",
            "message": f"Browser status check failed: {error_msg}"
        }

@app.post("/api/login", response_model=LoginResponse)
async def login():
    """Login to Reddit account"""
    try:
        # Re-import to ensure we have the latest version
        import service_mcp
        current_login_impl = getattr(service_mcp, 'login_impl', None)
        
        # Check if login_impl exists and is callable
        if current_login_impl is None:
            raise HTTPException(
                status_code=500, 
                detail="login_impl function not found in service_mcp module. Please check service_mcp.py"
            )
        
        if not callable(current_login_impl):
            raise HTTPException(
                status_code=500, 
                detail=f"login_impl is not callable. Type: {type(current_login_impl)}"
            )
        
        # Use the current version
        result = await current_login_impl()
        success = "success" in result.lower() or "logged in" in result.lower() or "already" in result.lower()
        return {
            "success": success,
            "message": result
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Login failed: {str(e)}\nTraceback: {traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail)

@app.post("/api/search-notes", response_model=SearchNotesResponse)
async def search_notes(request: SearchNotesRequest):
    """Search for Reddit posts by keywords"""
    try:
        result = await search_notes_impl(request.keywords, request.limit)
        
        # Parse the result string into structured data
        results = []
        if "Search results" in result:
            lines = result.split("\n")
            current_item = {}
            for line in lines:
                line = line.strip()
                if line and not line.startswith("Search results"):
                    if line[0].isdigit() and "." in line:
                        # New item
                        if current_item:
                            results.append(current_item)
                        parts = line.split(". ", 1)
                        if len(parts) == 2:
                            current_item = {"title": parts[1], "url": ""}
                    elif line.startswith("Link:"):
                        url = line.replace("Link:", "").strip()
                        if current_item:
                            current_item["url"] = url
        
        if current_item:
            results.append(current_item)
        
        return {
            "success": True,
            "results": results,
            "message": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/api/note-content", response_model=GetNoteContentResponse)
async def get_note_content(request: GetNoteContentRequest):
    """Get content of a specific Reddit post"""
    try:
        result = await get_note_content_impl(request.url)
        return {
            "success": True,
            "content": result,
            "message": "Content retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get note content: {str(e)}")

@app.post("/api/note-comments", response_model=GetCommentsResponse)
async def get_note_comments_endpoint(request: GetCommentsRequest):
    """Get comments for a specific Reddit post"""
    try:
        # Use _impl version to avoid FunctionTool wrapper
        if get_note_comments_impl is None:
            raise HTTPException(
                status_code=500, 
                detail="get_note_comments_impl function not found in service_mcp module"
            )
        
        if not callable(get_note_comments_impl):
            raise HTTPException(
                status_code=500, 
                detail=f"get_note_comments_impl is not callable. Type: {type(get_note_comments_impl)}"
            )
        
        result = await get_note_comments_impl(request.url)
        
        # Parse comments from result string
        comments = []
        if "comments" in result.lower():
            lines = result.split("\n")
            for line in lines:
                line = line.strip()
                if line and line[0].isdigit() and ". " in line:
                    # Parse comment format: "1. Username (Time): Content"
                    # Try both English and Chinese parentheses
                    parts = line.split(". ", 1)
                    if len(parts) == 2:
                        comment_text = parts[1]
                        # Try English parentheses first: "Username (Time): Content"
                        if "(" in comment_text and "):" in comment_text:
                            username_part = comment_text.split("(")[0].strip()
                            time_part = comment_text.split("(")[1].split(")")[0].strip()
                            content = comment_text.split("): ", 1)[1] if "): " in comment_text else ""
                            comments.append({
                                "username": username_part,
                                "time": time_part,
                                "content": content
                            })
                        # Try Chinese parentheses: "username（time）: content"
                        elif "（" in comment_text and "）:" in comment_text:
                            username_part = comment_text.split("（")[0].strip()
                            time_part = comment_text.split("（")[1].split("）")[0].strip()
                            content = comment_text.split("）: ", 1)[1] if "）: " in comment_text else ""
                            comments.append({
                                "username": username_part,
                                "time": time_part,
                                "content": content
                            })
        
        return {
            "success": True,
            "comments": comments,
            "message": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get comments: {str(e)}")

@app.post("/api/generate-comment", response_model=PostCommentResponse)
async def generate_comment(request: PostCommentRequest):
    """Generate a smart comment preview without posting"""
    try:
        # Import the internal function to generate comment without posting
        _generate_smart_comment = getattr(service_mcp, '_generate_smart_comment', None)
        get_note_content_impl = getattr(service_mcp, 'get_note_content_impl', None)
        
        if not _generate_smart_comment or not callable(_generate_smart_comment):
            raise HTTPException(status_code=500, detail="_generate_smart_comment not found")
        
        if not get_note_content_impl:
            raise HTTPException(status_code=500, detail="get_note_content_impl not found")
        
        # Get post content - we need structured data (Title, Content, Author)
        # The post_smart_comment function gets this data, so we'll replicate that logic
        # For now, we'll use get_note_content_impl and parse it, or visit the page directly
        # Actually, let's just visit the page and extract the data like post_smart_comment does
        from service_mcp import ensure_browser, main_page
        
        login_status = await ensure_browser()
        if not login_status:
            raise HTTPException(status_code=400, detail="Please login to Reddit first")
        
        # Visit post link to get structured content
        await main_page.goto(request.url, timeout=60000)
        await asyncio.sleep(3)
        
        # Extract post content similar to post_smart_comment
        post_content = {
            "Title": "",
            "Content": "",
            "Author": ""
        }
        
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
        except:
            pass
        
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
        except:
            pass
        
        # Get post body content
        try:
            content_selectors = [
                'div[data-testid="post-content"]',
                'div[data-testid="post-content"] p',
                'article p',
                'div.usertext-body'
            ]
            for selector in content_selectors:
                try:
                    content_elements = await main_page.query_selector_all(selector)
                    if content_elements:
                        content_parts = []
                        for el in content_elements[:5]:  # Limit to first 5 paragraphs
                            text = await el.text_content()
                            if text and text.strip():
                                content_parts.append(text.strip())
                        if content_parts:
                            post_content["Content"] = " ".join(content_parts)
                            break
                except:
                    continue
        except:
            pass
        
        # If no content found, use title as content
        if not post_content["Content"]:
            post_content["Content"] = post_content["Title"] or "Post content"
        
        # Generate comment text
        comment_text = await _generate_smart_comment(post_content, request.comment_type)
        
        return {
            "success": True,
            "message": comment_text,
            "comment": comment_text
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Failed to generate comment: {str(e)}\n{traceback.format_exc()}")

@app.post("/api/post-comment", response_model=PostCommentResponse)
async def post_comment(request: PostCommentRequest):
    """Post a smart comment on a Reddit post"""
    try:
        # Use _impl version to avoid FunctionTool wrapper from @mcp.tool() decorator
        if post_smart_comment_impl is None:
            raise HTTPException(status_code=500, detail="post_smart_comment_impl not found")
        
        # Pass comment_text if provided to avoid regenerating it
        result = await post_smart_comment_impl(request.url, request.comment_type, request.comment_text)
        success = "success" in result.lower() or "posted" in result.lower() or "commented" in result.lower()
        return {
            "success": success,
            "message": result
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Failed to post comment: {str(e)}\n{traceback.format_exc()}")

@app.post("/api/reply-comment", response_model=ReplyCommentResponse)
async def reply_comment(request: ReplyCommentRequest):
    """Reply to a specific comment"""
    try:
        result = await reply_to_comment(request.url, request.comment_content, request.reply_text)
        success = "success" in result.lower()
        return {
            "success": success,
            "message": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reply to comment: {str(e)}")

@app.post("/api/generate-keywords", response_model=GenerateKeywordsResponse)
async def generate_keywords(request: GenerateKeywordsRequest):
    """Generate search keywords from product description"""
    try:
        # Use _impl version to avoid FunctionTool wrapper
        if generate_search_keywords_impl is None:
            raise HTTPException(
                status_code=500, 
                detail="generate_search_keywords_impl function not found in service_mcp module"
            )
        
        if not callable(generate_search_keywords_impl):
            raise HTTPException(
                status_code=500, 
                detail=f"generate_search_keywords_impl is not callable. Type: {type(generate_search_keywords_impl)}"
            )
        
        result = await generate_search_keywords_impl(request.product_description)
        # Extract keywords from result
        keywords = result.replace("Search keywords generated from product description:", "").strip()
        return {
            "success": True,
            "keywords": keywords,
            "message": result
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate keywords: {str(e)}")

@app.post("/api/auto-promote", response_model=AutoPromoteResponse)
async def auto_promote(request: AutoPromoteRequest):
    """Automatically promote product by searching posts, analyzing comments, and replying"""
    try:
        result = await auto_promote_product(
            request.product_description,
            request.search_keywords or "",
            request.max_posts,
            request.min_match_score
        )
        return {
            "success": True,
            "report": result,
            "message": "Auto promotion completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto promotion failed: {str(e)}")

@app.post("/api/analyze-product", response_model=AnalyzeProductResponse)
async def analyze_product(request: AnalyzeProductRequest):
    """Analyze product: search posts, get content, get comments, and analyze intent"""
    try:
        # Step 1: Generate search keywords
        if generate_search_keywords_impl is None:
            raise HTTPException(status_code=500, detail="generate_search_keywords_impl not found")
        
        keywords_result = await generate_search_keywords_impl(request.product_description)
        keywords = keywords_result.replace("Search keywords generated from product description:", "").strip()
        
        # Step 2: Search for posts
        if search_notes_impl is None:
            raise HTTPException(status_code=500, detail="search_notes_impl not found")
        
        search_result = await search_notes_impl(keywords, limit=1)
        if not search_result or not isinstance(search_result, str) or "No posts found" in search_result:
            return {
                "success": True,
                "leads": [],
                "message": "No posts found matching the product description"
            }
        
        # Parse search result string into list of dictionaries
        # Format: "Search results:\n\n1. Title\n   Link: URL\n\n2. Title\n   Link: URL\n\n..."
        posts = []
        import re
        lines = search_result.split('\n')
        current_title = None
        for line in lines:
            line = line.strip()
            # Match numbered title: "1. Title" or "1. "Title""
            title_match = re.match(r'^\d+\.\s+(.+)$', line)
            if title_match:
                current_title = title_match.group(1).strip()
                # Remove quotes if present
                if current_title.startswith('"') and current_title.endswith('"'):
                    current_title = current_title[1:-1]
            # Match link: "Link: URL"
            elif line.startswith('Link:') and current_title:
                url = line.replace('Link:', '').strip()
                if url and current_title:
                    posts.append({'title': current_title, 'url': url})
                    current_title = None
        
        if not posts:
            return {
                "success": True,
                "leads": [],
                "message": "No posts found matching the product description"
            }
        
        # Step 3: Process each post in parallel for better performance
        # Use asyncio to parallelize post processing
        async def process_single_post(i: int, post: dict, product_description: str) -> list:
            """Process a single post and return its leads"""
            post_leads = []
            try:
                post_url = post.get('url', '')
                post_title = post.get('title', '')
                
                if not post_url:
                    return post_leads
                
                # Get post content
                post_content = ""
                if get_note_content_impl:
                    content_result = await get_note_content_impl(post_url)
                    post_content = content_result if isinstance(content_result, str) else str(content_result)
                
                # Get comments - use _get_note_comments_structured directly for structured data
                comments = []
                try:
                    _get_note_comments_structured = getattr(service_mcp, '_get_note_comments_structured', None)
                    if _get_note_comments_structured and callable(_get_note_comments_structured):
                        comments = await _get_note_comments_structured(post_url)
                    elif get_note_comments_impl:
                        # Fallback to impl version if structured version not available
                        comments_result = await get_note_comments_impl(post_url)
                        if isinstance(comments_result, list):
                            comments = comments_result
                        elif isinstance(comments_result, str):
                            # Try to parse from string format
                            import re
                            lines = comments_result.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and line[0].isdigit() and '.' in line:
                                    parts = line.split('. ', 1)
                                    if len(parts) == 2:
                                        comment_text = parts[1]
                                        if ' (' in comment_text and '):' in comment_text:
                                            username_part = comment_text.split(' (')[0]
                                            time_part = comment_text.split(' (')[1].split('):')[0]
                                            content = comment_text.split('): ', 1)[1] if '): ' in comment_text else ''
                                            comments.append({
                                                'username': username_part,
                                                'time': time_part,
                                                'content': content
                                            })
                except Exception as e:
                    print(f"Error getting comments for {post_url}: {e}")
                    comments = []
                
                # Analyze intent for post content
                intent_score = await _analyze_intent_score(post_content, product_description)
                
                # Create lead for the post
                post_leads.append({
                    "id": f"post-{i}",
                    "username": extract_username_from_url(post_url) or "Reddit User",
                    "platform": "Reddit",
                    "category": "LIFESTYLE NOTE",
                    "date": post.get('date', ''),
                    "title": post_title,
                    "question": post_title,
                    "content": post_content[:500] if post_content else "",
                    "url": post_url,
                    "intentScore": intent_score,
                    "type": "post"
                })
                
                # Process comments in parallel for intent analysis
                async def process_comment(j: int, comment: dict) -> Optional[dict]:
                    """Process a single comment and return lead if intent is high enough"""
                    comment_content = comment.get('content', '') or comment.get('Content', '')
                    comment_username = comment.get('username', '') or comment.get('Username', '')
                    
                    if not comment_content:
                        return None
                    
                    # Analyze comment intent
                    comment_intent = await _analyze_intent_score(comment_content, product_description)
                    
                    if comment_intent >= 40:  # Only include comments with reasonable intent
                        # Create comment URL
                        comment_url = post_url
                        if '/comments/' in post_url:
                            comment_url = post_url.split('?')[0] + f'#comment-{j}'
                        
                        return {
                            "id": f"comment-{i}-{j}",
                            "username": comment_username or "Unknown User",
                            "platform": "Reddit",
                            "category": "LIFESTYLE NOTE",
                            "date": comment.get('time', '') or comment.get('Time', ''),
                            "title": "",
                            "question": extract_question(comment_content),
                            "content": comment_content,
                            "url": comment_url,
                            "intentScore": comment_intent,
                            "type": "comment"
                        }
                    return None
                
                # Process all comments in parallel
                comment_tasks = [process_comment(j, comment) for j, comment in enumerate(comments[:10])]  # Limit to 10 comments per post
                comment_results = await asyncio.gather(*comment_tasks, return_exceptions=True)
                
                # Collect valid comment leads
                for result in comment_results:
                    if isinstance(result, Exception):
                        continue
                    if result is not None:
                        post_leads.append(result)
                
            except Exception as e:
                print(f"Error processing post {i}: {e}")
            
            return post_leads
        
        # Process all posts in parallel
        parallel_start = time.time()
        post_tasks = [process_single_post(i, post, request.product_description) for i, post in enumerate(posts[:5])]  # Limit to 5 posts
        post_results = await asyncio.gather(*post_tasks, return_exceptions=True)
        parallel_time = time.time() - parallel_start
        print(f"[TIMING] Parallel post processing took: {parallel_time:.2f}s")
        
        # Flatten results from all posts
        leads = []
        for result in post_results:
            if isinstance(result, Exception):
                print(f"Error in post processing: {result}")
                continue
            if isinstance(result, list):
                leads.extend(result)
        
        # Sort by intent score
        leads.sort(key=lambda x: x.get('intentScore', 0), reverse=True)
        
        return {
            "success": True,
            "leads": leads,
            "message": f"Found {len(leads)} potential leads"
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}\n{traceback.format_exc()}")

async def _analyze_intent_score(text: str, product_description: str) -> int:
    """Analyze intent score using LLM"""
    try:
        # Import _call_llm from service_mcp
        _call_llm = getattr(service_mcp, '_call_llm', None)
        if _call_llm and callable(_call_llm):
            prompt = f"""Analyze the following text and determine the purchase intent score (0-100) for this product:

Product: {product_description}

Text to analyze: {text[:500]}

Respond with ONLY a number between 0 and 100 representing the intent score. Higher scores indicate stronger purchase intent."""
            
            result = await _call_llm(prompt, system_prompt="You are an expert at analyzing purchase intent. Respond with only a number.")
            
            # Try to extract number from result
            import re
            numbers = re.findall(r'\d+', result)
            if numbers:
                score = int(numbers[0])
                return min(100, max(0, score))
        
        # Fallback: simple keyword-based scoring
        text_lower = text.lower()
        score = 0
        intent_keywords = ['recommend', 'recommendation', 'need', 'want', 'looking for', 'best', 'which', 'where to buy', 'help me find', 'seeking', 'searching for']
        for keyword in intent_keywords:
            if keyword in text_lower:
                score += 15
        if '?' in text:
            score += 10
        return min(100, max(20, score))
    except Exception as e:
        print(f"Error analyzing intent: {e}")
        # Fallback scoring
        text_lower = text.lower()
        score = 0
        intent_keywords = ['recommend', 'need', 'want', 'looking for', 'best', 'which', 'where to buy']
        for keyword in intent_keywords:
            if keyword in text_lower:
                score += 15
        return min(100, max(20, score))

def extract_username_from_url(url: str) -> Optional[str]:
    """Extract username from Reddit URL"""
    import re
    match = re.search(r'/u/([^/]+)', url) or re.search(r'/user/([^/]+)', url)
    return match.group(1) if match else None

def extract_question(text: str) -> str:
    """Extract question from text"""
    if not text:
        return ""
    sentences = text.split('.')
    for sentence in sentences:
        if '?' in sentence:
            return sentence.strip() + '?'
    return text[:100] + '...' if len(text) > 100 else text

# Run the server
if __name__ == "__main__":
    # Ensure event loop policy is set before uvicorn starts
    if platform.system() == "Windows":
        if sys.version_info >= (3, 8):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        else:
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)
    
    uvicorn.run(
        "backend:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

