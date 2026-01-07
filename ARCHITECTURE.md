# Architecture Overview

## Current State

### Problem
- `service_mcp.py` contains **only Reddit-specific** implementation
- `RedditPlatform` is a thin wrapper around `service_mcp.py` functions
- Other platforms (Twitter, Instagram, etc.) are empty skeletons
- This creates tight coupling and makes it unclear where platform code should live

### Current Architecture

```
service_mcp.py (Reddit-specific)
    ├── Reddit login, search, comments, posting logic
    ├── Browser management (shared)
    ├── LLM functions (shared)
    └── MCP server tools (Reddit-specific)

platforms/
    ├── RedditPlatform (wraps service_mcp functions)
    ├── TwitterPlatform (empty skeleton)
    ├── InstagramPlatform (empty skeleton)
    └── ... (other empty skeletons)
```

## Recommended Architecture

### Option 1: Keep service_mcp.py for Reddit (Current - Pragmatic)
**Pros:**
- Minimal refactoring needed
- Backward compatible
- Reddit functionality already works

**Cons:**
- Reddit code not in RedditPlatform
- Inconsistent with other platforms
- Tight coupling

**Best for:** Quick implementation, maintaining existing Reddit functionality

### Option 2: Move Reddit to RedditPlatform (Ideal - Clean)
**Pros:**
- All platform code in platform classes
- Consistent architecture
- Easy to add new platforms
- Clear separation of concerns

**Cons:**
- Requires significant refactoring
- Need to maintain MCP server compatibility
- More work upfront

**Best for:** Long-term maintainability, true multi-platform support

### Option 3: Hybrid Approach (Recommended)
**Structure:**
```
service_mcp.py
    ├── Shared utilities (browser management, LLM)
    ├── MCP server setup
    └── Legacy Reddit functions (deprecated, use RedditPlatform)

platforms/
    ├── RedditPlatform (full Reddit implementation)
    ├── TwitterPlatform (full Twitter implementation)
    └── ... (each platform is self-contained)
```

**Benefits:**
- Each platform is self-contained
- Shared utilities in service_mcp
- Can gradually migrate Reddit code
- Clear where to implement new platforms

## Implementation Strategy

### For New Platforms (Twitter, Instagram, etc.)
1. **Implement directly in platform class** - Don't add to service_mcp.py
2. **Use shared utilities** - Import browser/LLM helpers from service_mcp if needed
3. **Self-contained** - Each platform should work independently

### For Reddit (Migration Path)
1. **Phase 1 (Current):** RedditPlatform wraps service_mcp functions ✅
2. **Phase 2 (Future):** Move Reddit logic from service_mcp.py to RedditPlatform
3. **Phase 3 (Future):** Keep service_mcp.py only for shared utilities and MCP server

## Current Status

- ✅ Platform abstraction layer created
- ✅ RedditPlatform wraps existing Reddit code
- ✅ Other platforms have skeleton implementations
- ⚠️ Reddit code still in service_mcp.py (not ideal but works)
- ✅ Architecture ready for new platform implementations

## Next Steps

1. **For immediate use:** Current architecture works - RedditPlatform wraps service_mcp
2. **For new platforms:** Implement directly in platform classes (TwitterPlatform, etc.)
3. **For future refactoring:** Gradually move Reddit code from service_mcp.py to RedditPlatform

