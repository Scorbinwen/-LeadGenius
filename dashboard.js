/**
 * Dashboard JavaScript
 * Handles all API interactions on the dashboard page
 */

// Check API status on page load
window.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    // Load analyzed leads from sessionStorage if available
    loadAnalyzedLeads();
});

// Load analyzed leads from sessionStorage
function loadAnalyzedLeads() {
    try {
        const storedLeads = sessionStorage.getItem('analyzedLeads');
        if (storedLeads) {
            const leads = JSON.parse(storedLeads);
            if (Array.isArray(leads) && leads.length > 0) {
                // Add to discovered leads
                discoveredLeads = [...leads];
                updateLeadsCount();
                renderLeads();
                // Clear sessionStorage after loading
                sessionStorage.removeItem('analyzedLeads');
            }
        }
    } catch (error) {
        console.error('Error loading analyzed leads:', error);
    }
}

// Helper function to show result
function showResult(elementId, success, message, data = null) {
    const element = document.getElementById(elementId);
    const loading = document.getElementById(elementId.replace('Result', 'Loading'));
    
    if (loading) loading.classList.remove('show');
    
    element.className = 'result-box show ' + (success ? 'success' : 'error');
    
    let content = message;
    if (data) {
        if (typeof data === 'string') {
            content += '\n\n' + data;
        } else {
            content += '\n\n' + JSON.stringify(data, null, 2);
        }
    }
    
    element.innerHTML = `
        <div class="result-title">${success ? '✓ Success' : '✗ Error'}</div>
        <div class="result-content">${escapeHtml(content)}</div>
    `;
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Helper function to show loading
function showLoading(elementId, show = true) {
    const loading = document.getElementById(elementId);
    if (loading) {
        if (show) {
            loading.classList.add('show');
        } else {
            loading.classList.remove('show');
        }
    }
}

// Update API status indicator
function updateApiStatus(online) {
    const indicator = document.getElementById('apiStatus');
    const text = document.getElementById('apiStatusText');
    
    if (indicator && text) {
        indicator.className = 'status-indicator ' + (online ? 'online' : 'offline');
        text.textContent = online ? 'API Online' : 'API Offline';
    }
}

// Health Check
async function checkHealth() {
    showLoading('healthLoading', true);
    try {
        const result = await API.healthCheck();
        showResult('healthResult', true, result.message || 'API is healthy', result);
        updateApiStatus(true);
    } catch (error) {
        showResult('healthResult', false, error.message || 'API is not accessible');
        updateApiStatus(false);
    } finally {
        showLoading('healthLoading', false);
    }
}

// Login
async function login() {
    showLoading('loginLoading', true);
    try {
        const result = await API.login();
        showResult('loginResult', result.success, result.message);
    } catch (error) {
        showResult('loginResult', false, error.message || 'Login failed');
    } finally {
        showLoading('loginLoading', false);
    }
}

// Generate Keywords
async function generateKeywords() {
    const productDescription = document.getElementById('productDescription').value.trim();
    
    if (!productDescription) {
        alert('Please enter a product description');
        return;
    }
    
    showLoading('keywordsLoading', true);
    try {
        const result = await API.generateKeywords(productDescription);
        showResult('keywordsResult', result.success, result.message, { keywords: result.keywords });
    } catch (error) {
        showResult('keywordsResult', false, error.message || 'Failed to generate keywords');
    } finally {
        showLoading('keywordsLoading', false);
    }
}

// Store discovered leads
let discoveredLeads = [];
let activeTab = 'all';

// Search Notes - now creates lead cards
async function searchNotes() {
    const keywords = document.getElementById('searchKeywords').value.trim();
    const limit = parseInt(document.getElementById('searchLimit').value) || 10;
    
    if (!keywords) {
        alert('Please enter search keywords');
        return;
    }
    
    showLoading('searchLoading', true);
    try {
        const result = await API.searchNotes(keywords, limit);
        if (result.success && result.results && result.results.length > 0) {
            // Convert search results to lead cards
            const newLeads = result.results.map((item, index) => ({
                id: `lead-${Date.now()}-${index}`,
                username: extractUsernameFromUrl(item.url) || 'Reddit User',
                platform: 'Reddit',
                category: 'LIFESTYLE NOTE',
                date: new Date().toISOString().split('T')[0],
                title: item.title || 'Untitled Post',
                question: item.title || '',
                content: '',
                url: item.url,
                intentScore: calculateIntentScore(item.title || ''),
                type: 'post'
            }));
            
            // Add to discovered leads
            discoveredLeads = [...discoveredLeads, ...newLeads];
            updateLeadsCount();
            renderLeads();
            
            showResult('searchResult', true, `Found ${result.results.length} result${result.results.length > 1 ? 's' : ''}. Added to Discovered Leads.`, null);
        } else {
            showResult('searchResult', true, result.message || 'No results found');
        }
    } catch (error) {
        showResult('searchResult', false, error.message || 'Search failed');
    } finally {
        showLoading('searchLoading', false);
    }
}

// Get Note Content
async function getNoteContent() {
    const url = document.getElementById('noteUrl').value.trim();
    
    if (!url) {
        alert('Please enter a note URL');
        return;
    }
    
    showLoading('contentLoading', true);
    try {
        const result = await API.getNoteContent(url);
        showResult('contentResult', result.success, result.content || result.message);
    } catch (error) {
        showResult('contentResult', false, error.message || 'Failed to get note content');
    } finally {
        showLoading('contentLoading', false);
    }
}

// Get Comments - now extracts high-intent users and creates lead cards
async function getComments() {
    const url = document.getElementById('commentsUrl').value.trim();
    
    if (!url) {
        alert('Please enter a note URL');
        return;
    }
    
    showLoading('commentsLoading', true);
    try {
        const result = await API.getNoteComments(url);
        if (result.success && result.comments && result.comments.length > 0) {
            // Analyze comments for high-intent users
            const highIntentKeywords = [
                'recommend', 'recommendation', 'suggest', 'looking for', 'need', 'want', 
                'best', 'which', 'where to buy', 'where can i', 'help me find',
                'seeking', 'searching for', 'trying to find', 'anyone know', 'any suggestions'
            ];
            
            const newLeads = result.comments
                .map((comment, index) => {
                    const content = (comment.content || '').toLowerCase();
                    const hasIntent = highIntentKeywords.some(keyword => content.includes(keyword));
                    const intentScore = hasIntent ? calculateIntentScore(comment.content) : Math.floor(Math.random() * 40) + 20;
                    
                    // Create comment URL (Reddit comment permalink format)
                    // Reddit URLs: https://www.reddit.com/r/subreddit/comments/POST_ID/TITLE/comment/COMMENT_ID/
                    let commentUrl = url;
                    if (url.includes('/comments/')) {
                        const parts = url.split('/comments/');
                        const postPart = parts[1].split('/')[0]; // Get post ID
                        // Use the post URL as base, comment links are typically in format: /r/subreddit/comments/POST_ID/TITLE/comment/COMMENT_ID/
                        commentUrl = url.split('?')[0]; // Remove query params
                        if (!commentUrl.endsWith('/')) commentUrl += '/';
                        commentUrl += `comment/${comment.id || `c${index}`}/`;
                    } else {
                        commentUrl = url + (url.includes('#') ? '' : '#') + `comment-${index}`;
                    }
                    
                    return {
                        id: `lead-comment-${Date.now()}-${index}`,
                        username: comment.username || 'Unknown User',
                        platform: 'Reddit',
                        category: 'LIFESTYLE NOTE',
                        date: comment.time || new Date().toISOString().split('T')[0],
                        title: '',
                        question: extractQuestion(comment.content) || comment.content.substring(0, 100) + '...',
                        content: comment.content || '',
                        url: commentUrl,
                        intentScore: intentScore,
                        type: 'comment'
                    };
                })
                .filter(lead => lead.intentScore >= 40); // Only show leads with reasonable intent
            
            // Add to discovered leads
            discoveredLeads = [...discoveredLeads, ...newLeads];
            updateLeadsCount();
            renderLeads();
            
            const highIntentCount = newLeads.filter(l => l.intentScore >= 80).length;
            showResult('commentsResult', true, 
                `Found ${result.comments.length} comment${result.comments.length > 1 ? 's' : ''}. ` +
                `Identified ${newLeads.length} potential lead${newLeads.length > 1 ? 's' : ''} ` +
                `(${highIntentCount} high-intent). Added to Discovered Leads.`, null);
        } else {
            showResult('commentsResult', true, result.message || 'No comments found');
        }
    } catch (error) {
        showResult('commentsResult', false, error.message || 'Failed to get comments');
    } finally {
        showLoading('commentsLoading', false);
    }
}

// Post Comment
async function postComment() {
    const url = document.getElementById('postCommentUrl').value.trim();
    const commentType = document.getElementById('commentType').value;
    
    if (!url) {
        alert('Please enter a note URL');
        return;
    }
    
    showLoading('postCommentLoading', true);
    try {
        const result = await API.postComment(url, commentType);
        showResult('postCommentResult', result.success, result.message);
    } catch (error) {
        showResult('postCommentResult', false, error.message || 'Failed to post comment');
    } finally {
        showLoading('postCommentLoading', false);
    }
}

// Reply to Comment
async function replyToComment() {
    const url = document.getElementById('replyUrl').value.trim();
    const commentContent = document.getElementById('commentContent').value.trim();
    const replyText = document.getElementById('replyText').value.trim();
    
    if (!url) {
        alert('Please enter a note URL');
        return;
    }
    
    if (!commentContent) {
        alert('Please enter the comment content to reply to');
        return;
    }
    
    if (!replyText) {
        alert('Please enter your reply text');
        return;
    }
    
    showLoading('replyLoading', true);
    try {
        const result = await API.replyToComment(url, commentContent, replyText);
        showResult('replyResult', result.success, result.message);
    } catch (error) {
        showResult('replyResult', false, error.message || 'Failed to reply to comment');
    } finally {
        showLoading('replyLoading', false);
    }
}

// Auto Promote - extracts leads from results
async function autoPromote() {
    const productDescription = document.getElementById('autoPromoteDescription').value.trim();
    const searchKeywords = document.getElementById('autoPromoteKeywords').value.trim();
    const maxPosts = parseInt(document.getElementById('maxPosts').value) || 5;
    const minMatchScore = parseFloat(document.getElementById('minMatchScore').value) || 40.0;
    
    if (!productDescription) {
        alert('Please enter a product description');
        return;
    }
    
    if (!confirm(`This will process up to ${maxPosts} posts. This may take several minutes. Continue?`)) {
        return;
    }
    
    showLoading('autoPromoteLoading', true);
    try {
        const result = await API.autoPromote(
            productDescription,
            searchKeywords || '',
            maxPosts,
            minMatchScore
        );
        
        // Parse auto-promote results to extract leads
        // The result.report should contain information about discovered leads
        if (result.success && result.report) {
            // Try to extract lead information from the report
            // This would need to be customized based on actual API response format
            const reportText = result.report.toLowerCase();
            if (reportText.includes('found') || reportText.includes('lead')) {
                // Extract leads from report if available
                // For now, we'll just show the report
            }
        }
        
        showResult('autoPromoteResult', result.success, result.report || result.message);
    } catch (error) {
        showResult('autoPromoteResult', false, error.message || 'Auto promotion failed');
    } finally {
        showLoading('autoPromoteLoading', false);
    }
}

// Helper functions for lead management
function extractUsernameFromUrl(url) {
    try {
        const match = url.match(/\/u\/([^\/]+)/) || url.match(/\/user\/([^\/]+)/);
        return match ? match[1] : null;
    } catch {
        return null;
    }
}

function calculateIntentScore(text) {
    if (!text) return 0;
    const lowerText = text.toLowerCase();
    let score = 0;
    
    // High intent indicators
    const highIntent = ['recommend', 'recommendation', 'suggest', 'looking for', 'need', 'want', 'best', 'which', 'where to buy', 'help me find', 'seeking', 'searching for', 'trying to find', 'anyone know', 'any suggestions', 'please recommend', 'can anyone suggest'];
    highIntent.forEach(keyword => {
        if (lowerText.includes(keyword)) score += 15;
    });
    
    // Question marks indicate inquiry
    if (text.includes('?')) score += 10;
    
    // Urgency indicators
    const urgency = ['urgent', 'asap', 'soon', 'quickly', 'immediately', 'need help', 'desperate'];
    urgency.forEach(keyword => {
        if (lowerText.includes(keyword)) score += 10;
    });
    
    // Purchase intent
    const purchase = ['buy', 'purchase', 'price', 'cost', 'afford', 'budget', 'discount'];
    purchase.forEach(keyword => {
        if (lowerText.includes(keyword)) score += 12;
    });
    
    return Math.min(100, Math.max(20, score));
}

function extractQuestion(text) {
    if (!text) return '';
    // Find sentences with question marks
    const sentences = text.split(/[.!?]/);
    const question = sentences.find(s => s.includes('?'));
    return question ? question.trim() + '?' : text.substring(0, 100);
}

function updateLeadsCount() {
    const countEl = document.getElementById('leadsCount');
    if (countEl) {
        countEl.textContent = discoveredLeads.length.toString();
    }
}

function renderLeads() {
    const container = document.getElementById('leadsFeed');
    if (!container) return;
    
    const filteredLeads = activeTab === 'high' 
        ? discoveredLeads.filter(lead => lead.intentScore >= 80)
        : discoveredLeads;
    
    // Sort by intent score (highest first)
    filteredLeads.sort((a, b) => b.intentScore - a.intentScore);
    
    if (filteredLeads.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <p>No ${activeTab === 'high' ? 'high-intent ' : ''}leads discovered yet. Start searching to find users!</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filteredLeads.map(lead => `
        <div class="lead-card">
            <div class="lead-header">
                <div class="lead-user-info">
                    <div class="lead-avatar">${(lead.username || 'U').charAt(0).toUpperCase()}</div>
                    <div class="lead-user-details">
                        <div class="lead-username">${escapeHtml(lead.username || 'Unknown User')}</div>
                        <div class="lead-meta">
                            <span class="lead-platform">${lead.platform || 'Reddit'}</span>
                            <span>•</span>
                            <span>${lead.category || 'LIFESTYLE NOTE'}</span>
                            <span>•</span>
                            <span>${lead.date || new Date().toISOString().split('T')[0]}</span>
                        </div>
                    </div>
                </div>
                ${lead.intentScore >= 80 ? `<div class="lead-intent-badge">${lead.intentScore}% INTENT</div>` : ''}
            </div>
            <div class="lead-content">
                ${lead.question ? `<div class="lead-question">${escapeHtml(lead.question)}</div>` : ''}
                ${lead.content ? `<div class="lead-text">${escapeHtml(lead.content.length > 200 ? lead.content.substring(0, 200) + '...' : lead.content)}</div>` : ''}
            </div>
            <div class="lead-footer">
                <a href="${escapeHtml(lead.url)}" target="_blank" rel="noopener noreferrer" class="lead-url">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                        <polyline points="15 3 21 3 21 9"></polyline>
                        <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                    View ${lead.type === 'comment' ? 'Comment' : 'Post'}
                </a>
            </div>
        </div>
    `).join('');
}

// Tab switching
function setActiveTab(tab) {
    activeTab = tab;
    const tabs = document.querySelectorAll('.feed-tab');
    tabs.forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    renderLeads();
}

// Make functions globally available
window.setActiveTab = setActiveTab;
window.renderLeads = renderLeads;
window.discoveredLeads = discoveredLeads;

