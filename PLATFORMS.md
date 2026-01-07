# Multi-Platform Support Architecture

## Overview

The system now supports multiple forum platforms through a modular architecture. Each platform is implemented as a separate class that inherits from `BasePlatform`.

## Architecture

### Platform Structure

```
platforms/
├── __init__.py              # Platform module exports
├── base_platform.py         # Abstract base class for all platforms
├── platform_registry.py     # Registry for managing platform instances
├── reddit_platform.py      # Reddit implementation (fully functional)
├── twitter_platform.py      # Twitter/X implementation (skeleton)
├── instagram_platform.py    # Instagram implementation (skeleton)
├── quora_platform.py        # Quora implementation (skeleton)
├── linkedin_platform.py     # LinkedIn implementation (skeleton)
└── tiktok_platform.py       # TikTok implementation (skeleton)
```

### Base Platform Interface

All platforms must implement the `BasePlatform` interface with these methods:

- `get_platform_name()` - Return platform identifier
- `get_base_url()` - Return platform base URL
- `ensure_browser()` - Initialize browser
- `login()` - Login to platform
- `search_posts(keywords, limit)` - Search for posts
- `get_post_content(url)` - Get post content
- `get_post_comments(url)` - Get post comments
- `post_comment(url, comment_text, comment_type)` - Post a comment
- `reply_to_comment(url, comment_content, reply_text)` - Reply to a comment

### Platform Registry

The `PlatformRegistry` manages platform instances:

- `get_platform(name, browser_context, main_page)` - Get or create platform instance
- `get_available_platforms()` - List all available platforms
- `register_platform(name, platform_class)` - Register a new platform

## Current Status

### ✅ Fully Implemented
- **Reddit** - Complete implementation (wraps service_mcp.py functions)
  - Note: Reddit-specific code is currently in `service_mcp.py`
  - `RedditPlatform` acts as a wrapper/adapter
  - This works but is not ideal - see ARCHITECTURE.md for details

### 🚧 Skeleton Implementations (Ready for Development)
- **Twitter/X** - Base structure ready (implement directly in TwitterPlatform)
- **Instagram** - Base structure ready (implement directly in InstagramPlatform)
- **Quora** - Base structure ready (implement directly in QuoraPlatform)
- **LinkedIn** - Base structure ready (implement directly in LinkedInPlatform)
- **TikTok** - Base structure ready (implement directly in TikTokPlatform)

## Important Note

**`service_mcp.py` is currently Reddit-specific.** For new platforms:
- ✅ Implement directly in the platform class (e.g., `TwitterPlatform`)
- ❌ Don't add platform-specific code to `service_mcp.py`
- ✅ Use shared utilities from `service_mcp.py` if needed (browser management, LLM)

See `ARCHITECTURE.md` for detailed architecture explanation and migration strategy.

## API Changes

### New Endpoint
- `GET /api/platforms` - Returns list of available platforms

### Updated Endpoints
- `POST /api/analyze-product` - Now accepts `platform` parameter (defaults to "reddit")

## Usage

### Backend API

```python
# Get available platforms
GET /api/platforms

# Analyze product on specific platform
POST /api/analyze-product
{
    "product_description": "Your product description",
    "platform": "reddit"  # or "twitter", "instagram", etc.
}
```

### Adding a New Platform

1. Create a new file in `platforms/` directory (e.g., `newplatform_platform.py`)
2. Inherit from `BasePlatform` and implement all abstract methods
3. Register in `platform_registry.py`:

```python
from .newplatform_platform import NewPlatformPlatform

_platforms: Dict[str, Type[BasePlatform]] = {
    ...
    'newplatform': NewPlatformPlatform,
}
```

## Next Steps

To implement a new platform:

1. Study the Reddit implementation as a reference
2. Implement platform-specific selectors and logic
3. Test with the platform's actual website structure
4. Handle platform-specific authentication if needed
5. Update frontend to show platform-specific UI if needed

