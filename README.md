# LeadGen AI - AI-Powered Lead Generation Website

A modern, responsive website inspired by leado.co, featuring all the vital components for an AI-powered lead generation service.

## Features

✨ **Complete Website Components:**
- **Hero Section** - Compelling headline with gradient text, CTAs, and statistics
- **Features Section** - 6 key features with icons and descriptions
- **How It Works** - 3-step process explanation
- **Testimonials** - Customer reviews and ratings
- **Pricing** - Three-tier pricing structure (Starter, Professional, Enterprise)
- **Contact Form** - Functional contact form with validation
- **Footer** - Complete footer with links to legal pages and company info

🎨 **Design Features:**
- Modern, clean UI with gradient accents
- Fully responsive design (mobile, tablet, desktop)
- Smooth animations and transitions
- Interactive elements and hover effects
- Professional color scheme
- Beautiful typography using Inter font

⚡ **Interactive Features:**
- Mobile-responsive navigation menu
- Smooth scrolling to sections
- Form validation
- Animated statistics counters
- Scroll-triggered animations
- Active navigation highlighting
- Parallax effects

## Getting Started

### Prerequisites

**For Frontend Only:**
- No special prerequisites needed! This is a static website that works in any modern browser.

**For Full Stack (with Backend):**
- Python 3.8 or higher
- pip (Python package manager)
- Node.js (optional, for development)

### Installation

#### Frontend Only (Static Website)

1. Clone or download this repository
2. Open `index.html` in your web browser
3. That's it! The website is ready to use.

#### Full Stack Setup (with Backend API)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd FirstWebsite
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

4. **Configure environment variables**
   ```bash
   cp env.example .env
   # Edit .env and add your API keys and configuration
   ```

5. **Start the backend server**
   ```bash
   python backend.py
   ```
   The API will be available at `http://localhost:8000`

6. **Open the frontend**
   - Open `index.html` in your browser, or
   - Use a local server (recommended):
     ```bash
     # Using Python
     python -m http.server 8080
     
     # Or using Node.js
     npx serve .
     ```
   - Access at `http://localhost:8080`

7. **Update API URL (if needed)**
   - Edit `api.js` and change `API_BASE_URL` if your backend runs on a different port

### File Structure

```
FirstWebsite/
├── index.html          # Main HTML file
├── styles.css          # All CSS styles
├── script.js           # Frontend JavaScript
├── api.js              # API client for backend communication
├── backend.py          # FastAPI backend server
├── xiaohongshu_mcp.py  # Reddit scraping and automation logic
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── README.md           # This file
```

## Customization

### Colors

Edit the CSS variables in `styles.css` to change the color scheme:

```css
:root {
    --primary-color: #6366f1;
    --secondary-color: #8b5cf6;
    /* ... more variables */
}
```

### Content

- Edit `index.html` to change text content, sections, or structure
- Modify `styles.css` to adjust styling and layout
- Update `script.js` to add or modify interactive features

### Adding New Sections

1. Add HTML structure in `index.html`
2. Style it in `styles.css`
3. Add any interactive features in `script.js`

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Technologies Used

### Frontend
- **HTML5** - Semantic markup
- **CSS3** - Modern styling with CSS Grid, Flexbox, and custom properties
- **JavaScript (ES6+)** - Vanilla JavaScript for interactivity
- **Google Fonts** - Inter font family

### Backend
- **FastAPI** - Modern Python web framework for building APIs
- **Playwright** - Browser automation for web scraping
- **Pydantic** - Data validation using Python type annotations
- **Uvicorn** - ASGI server for running FastAPI
- **Python-dotenv** - Environment variable management

## Features Breakdown

### Navigation
- Fixed navbar with smooth scroll
- Mobile hamburger menu
- Active section highlighting

### Hero Section
- Eye-catching headline with gradient text
- Multiple CTAs
- Animated statistics
- Dashboard preview visual

### Features
- 6 feature cards with icons
- Hover effects
- Responsive grid layout

### How It Works
- 3-step process visualization
- Numbered steps with gradient circles
- CTA box at the end

### Testimonials
- Customer reviews with ratings
- Author avatars and information
- Card-based layout

### Pricing
- 3 pricing tiers
- Featured plan highlighting
- Feature lists
- CTA buttons

### Contact
- Contact form with validation
- Contact information display
- Responsive two-column layout

### Footer
- Company information
- Organized link sections
- Legal page links

## Backend API Endpoints

The backend provides the following REST API endpoints:

### Authentication
- `POST /api/login` - Login to Reddit account

### Search & Content
- `POST /api/search-notes` - Search for notes by keywords
- `POST /api/note-content` - Get content of a specific note
- `POST /api/note-comments` - Get comments for a note

### Engagement
- `POST /api/post-comment` - Post a smart comment on a note
- `POST /api/reply-comment` - Reply to a specific comment

### Automation
- `POST /api/generate-keywords` - Generate search keywords from product description
- `POST /api/auto-promote` - Automatically promote product (search, analyze, reply)

### Health
- `GET /health` - Health check endpoint
- `GET /` - Root endpoint

### API Documentation

Once the backend is running, you can access:
- **Interactive API Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative Docs**: `http://localhost:8000/redoc` (ReDoc)

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```env
# LLM Configuration
LLM_PROVIDER=ollama  # Options: "openai", "anthropic", or "ollama"
LLM_MODEL=Qwen2

# API Keys (if using OpenAI or Anthropic)
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434/v1
```

### LLM Provider Setup

**Option 1: Ollama (Recommended for local development)**
1. Install Ollama from https://ollama.ai
2. Pull a model: `ollama pull Qwen2`
3. Set `LLM_PROVIDER=ollama` in `.env`

**Option 2: OpenAI**
1. Get API key from https://platform.openai.com
2. Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` in `.env`

**Option 3: Anthropic**
1. Get API key from https://console.anthropic.com
2. Set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`

## Usage Examples

### Using the API from Frontend

```javascript
// Login
const loginResult = await API.login();

// Search notes
const searchResult = await API.searchNotes('skincare', 50);

// Get note content
const content = await API.getNoteContent('https://www.reddit.com/...');

// Generate keywords
const keywords = await API.generateKeywords('High-quality cotton T-shirt, multiple colors available');

// Auto promote product
const result = await API.autoPromote(
    'Natural organic face mask, hydrating and moisturizing',
    '',  // auto-generate keywords
    5,   // max posts
    40.0 // min match score
);
```

### Using the API with cURL

```bash
# Health check
curl http://localhost:8000/health

# Login
curl -X POST http://localhost:8000/api/login

# Search notes
curl -X POST http://localhost:8000/api/search-notes \
  -H "Content-Type: application/json" \
  -d '{"keywords": "skincare", "limit": 10}'

# Generate keywords
curl -X POST http://localhost:8000/api/generate-keywords \
  -H "Content-Type: application/json" \
  -d '{"product_description": "High-quality cotton T-shirt"}'
```

## Troubleshooting

### Backend won't start
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check that Playwright browsers are installed: `playwright install chromium`
- Verify your `.env` file is configured correctly

### CORS errors
- The backend is configured to allow all origins by default
- For production, update `allow_origins` in `backend.py`

### Browser automation issues
- Make sure you're logged into Reddit in the browser window that opens
- The browser runs in non-headless mode by default for easier debugging
- Check browser console for any errors

### API connection errors
- Verify the backend is running on `http://localhost:8000`
- Check `API_BASE_URL` in `api.js` matches your backend URL
- Ensure CORS is properly configured

## Future Enhancements

Potential additions you could make:
- User authentication and session management
- Dashboard functionality with real-time statistics
- WebSocket support for real-time updates
- Database integration for storing results
- Rate limiting and request queuing
- Background job processing
- Blog section
- Case studies page
- Live chat widget

## License

This project is open source and available for personal and commercial use.

## Credits

Inspired by leado.co - AI-powered lead generation platform.

---

Built with ❤️ using modern web technologies.

