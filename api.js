/**
 * API Client for LeadGen AI Backend
 * Handles all API calls to the backend server
 */

const API_BASE_URL = 'http://localhost:8000/api';

// Helper function for API calls
async function apiCall(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };

        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || error.message || 'API request failed');
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// API Functions
const API = {
    // Health check
    async healthCheck() {
        return await apiCall('/health', 'GET');
    },

    // Login to Reddit
    async login() {
        return await apiCall('/login', 'POST');
    },

    // Search Reddit posts
    async searchNotes(keywords, limit = 100) {
        return await apiCall('/search-notes', 'POST', {
            keywords,
            limit
        });
    },

    // Get Reddit post content
    async getNoteContent(url) {
        return await apiCall('/note-content', 'POST', { url });
    },

    // Get Reddit post comments
    async getNoteComments(url) {
        return await apiCall('/note-comments', 'POST', { url });
    },

    // Post smart comment
    async postComment(url, commentType = 'lead_gen') {
        return await apiCall('/post-comment', 'POST', {
            url,
            comment_type: commentType
        });
    },

    // Reply to comment
    async replyToComment(url, commentContent, replyText) {
        return await apiCall('/reply-comment', 'POST', {
            url,
            comment_content: commentContent,
            reply_text: replyText
        });
    },

    // Generate search keywords
    async generateKeywords(productDescription) {
        return await apiCall('/generate-keywords', 'POST', {
            product_description: productDescription
        });
    },

    // Auto promote product
    async autoPromote(productDescription, searchKeywords = '', maxPosts = 5, minMatchScore = 40.0) {
        return await apiCall('/auto-promote', 'POST', {
            product_description: productDescription,
            search_keywords: searchKeywords,
            max_posts: maxPosts,
            min_match_score: minMatchScore
        });
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = API;
}

