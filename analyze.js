/**
 * Analyze Product JavaScript
 * Handles product analysis workflow: login -> search -> analyze -> redirect to dashboard
 */

let isLoggedIn = false;
let currentStep = 0;

// Check login status on page load
window.addEventListener('DOMContentLoaded', async () => {
    await checkLoginStatus();
    updateAnalyzeButton();
});

// Check login status
async function checkLoginStatus() {
    try {
        const result = await API.healthCheck();
        // Try to check browser status to see if logged in
        try {
            const browserStatus = await fetch('http://localhost:8000/api/browser-status');
            const browserData = await browserStatus.json();
            // Check if browser is initialized and logged in
            if (browserData.status === 'ready' && browserData.message && 'Logged in: True' in browserData.message) {
                isLoggedIn = true;
                updateLoginStatus(true);
            } else {
                isLoggedIn = false;
                updateLoginStatus(false);
            }
        } catch {
            // If browser status check fails, assume not logged in
            isLoggedIn = false;
            updateLoginStatus(false);
        }
    } catch (error) {
        isLoggedIn = false;
        updateLoginStatus(false);
    }
}

// Update login status UI
function updateLoginStatus(loggedIn) {
    const statusEl = document.getElementById('loginStatus');
    const statusText = document.getElementById('loginStatusText');
    const loginBtn = document.getElementById('loginBtn');
    
    if (loggedIn) {
        statusEl.className = 'login-status logged-in';
        statusText.textContent = 'Logged in to Reddit';
        loginBtn.textContent = 'Logged In';
        loginBtn.disabled = true;
        isLoggedIn = true;
    } else {
        statusEl.className = 'login-status logged-out';
        statusText.textContent = 'Not logged in to Reddit';
        loginBtn.textContent = 'Login to Reddit';
        loginBtn.disabled = false;
        isLoggedIn = false;
    }
    updateAnalyzeButton();
}

// Handle login
async function handleLogin() {
    const loginBtn = document.getElementById('loginBtn');
    loginBtn.disabled = true;
    loginBtn.textContent = 'Logging in...';
    
    try {
        const result = await API.login();
        if (result.success) {
            updateLoginStatus(true);
        } else {
            showError(result.message || 'Login failed');
            updateLoginStatus(false);
        }
    } catch (error) {
        showError(error.message || 'Login failed');
        updateLoginStatus(false);
    } finally {
        loginBtn.disabled = false;
    }
}

// Update analyze button state
function updateAnalyzeButton() {
    const analyzeBtn = document.getElementById('analyzeBtn');
    const productDesc = document.getElementById('productDescription').value.trim();
    
    if (isLoggedIn && productDesc) {
        analyzeBtn.disabled = false;
    } else {
        analyzeBtn.disabled = true;
    }
}

// Listen to product description changes
document.getElementById('productDescription').addEventListener('input', updateAnalyzeButton);

// Handle form submission
async function handleAnalyze(event) {
    event.preventDefault();
    
    if (!isLoggedIn) {
        showError('Please login to Reddit first');
        return;
    }
    
    const websiteUrl = document.getElementById('websiteUrl').value.trim();
    const productDescription = document.getElementById('productDescription').value.trim();
    
    if (!productDescription) {
        showError('Please enter a product description');
        return;
    }
    
    // Show loading overlay
    const loadingOverlay = document.getElementById('loadingOverlay');
    loadingOverlay.classList.add('show');
    currentStep = 0;
    updateLoadingStep(0);
    
    try {
        // Update loading steps
        updateLoadingStep(1); // Searching for posts
        
        // Call analyze product endpoint
        const response = await fetch('http://localhost:8000/api/analyze-product', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                product_description: productDescription,
                website_url: websiteUrl || null
            })
        });
        
        updateLoadingStep(2); // Analyzing content
        updateLoadingStep(3); // Extracting comments
        updateLoadingStep(4); // Calculating intent
        
        const result = await response.json();
        
        if (result.success) {
            // Store leads in sessionStorage
            sessionStorage.setItem('analyzedLeads', JSON.stringify(result.leads));
            sessionStorage.setItem('productDescription', productDescription);
            
            // Redirect to dashboard
            window.location.href = 'dashboard.html';
        } else {
            showError(result.message || 'Analysis failed');
            loadingOverlay.classList.remove('show');
        }
    } catch (error) {
        showError(error.message || 'Analysis failed');
        loadingOverlay.classList.remove('show');
    }
}

// Update loading step
function updateLoadingStep(step) {
    const steps = ['step1', 'step2', 'step3', 'step4', 'step5'];
    steps.forEach((stepId, index) => {
        const stepEl = document.getElementById(stepId);
        if (stepEl) {
            if (index === step) {
                stepEl.classList.add('active');
            } else if (index < step) {
                stepEl.style.opacity = '0.5';
            } else {
                stepEl.style.opacity = '1';
                stepEl.classList.remove('active');
            }
        }
    });
    currentStep = step;
}

// Show error message
function showError(message) {
    const errorEl = document.getElementById('errorMessage');
    errorEl.textContent = message;
    errorEl.classList.add('show');
    
    setTimeout(() => {
        errorEl.classList.remove('show');
    }, 5000);
}

