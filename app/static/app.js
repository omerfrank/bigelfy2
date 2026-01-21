// CONFIGURATION
// Replace with your Manager VM Public IP
const API_BASE_URL = "https://151.145.82.67"; 

// If you registered the blueprint with a prefix (e.g., app.register_blueprint(auth_bp, url_prefix='/auth'))
// change this to '/auth'. If not, leave as empty string.
const AUTH_PREFIX = "/api/auth"; 

// STATE
let currentUser = null;

// --- DOM ELEMENTS ---
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const authSection = document.getElementById('auth-section');
const dashboardSection = document.getElementById('dashboard-section');
const authMessage = document.getElementById('auth-message');
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

// --- INITIALIZATION ---

// Check for existing session on page load (Cookies)
document.addEventListener('DOMContentLoaded', checkSession);

async function checkSession() {
    try {
        const res = await fetch(`${API_BASE_URL}${AUTH_PREFIX}/check`, {
            method: 'GET',
            credentials: 'include' // IMPORTANT: Sends the cookie
        });

        if (res.ok) {
            const data = await res.json();
            if (data.authenticated) {
                loginSuccess(data.user);
            }
        }
    } catch (err) {
        console.log("Session check failed", err);
    }
}

// --- AUTH LOGIC ---

function switchTab(tab) {
    authMessage.textContent = '';
    if (tab === 'login') {
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
        document.querySelectorAll('.tab-btn')[0].classList.add('active');
        document.querySelectorAll('.tab-btn')[1].classList.remove('active');
    } else {
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
        document.querySelectorAll('.tab-btn')[0].classList.remove('active');
        document.querySelectorAll('.tab-btn')[1].classList.add('active');
    }
}

// Login Handler
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
        const res = await fetch(`${API_BASE_URL}${AUTH_PREFIX}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include', // IMPORTANT: Receives the session cookie
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();

        if (res.ok) {
            loginSuccess(username);
        } else {
            showError(data.error || "Login failed");
        }
    } catch (err) {
        showError("Server error: " + err.message);
    }
});

// Register Handler
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('reg-username').value;
    const email = document.getElementById('reg-email').value;
    const password = document.getElementById('reg-password').value;

    try {
        const res = await fetch(`${API_BASE_URL}${AUTH_PREFIX}/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username, email, password })
        });

        const data = await res.json();

        if (res.ok) {
            alert("Account created! Please login.");
            switchTab('login');
        } else {
            showError(data.error || "Registration failed");
        }
    } catch (err) {
        showError("Server error: " + err.message);
    }
});

function loginSuccess(username) {
    currentUser = username;
    document.getElementById('display-username').textContent = username;
    authSection.classList.add('hidden');
    dashboardSection.classList.remove('hidden');
}

async function logout() {
    try {
        await fetch(`${API_BASE_URL}${AUTH_PREFIX}/logout`, { 
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        console.error("Logout error", err);
    } finally {
        // Clear UI regardless of server response
        currentUser = null;
        dashboardSection.classList.add('hidden');
        authSection.classList.remove('hidden');
        switchTab('login');
    }
}

function showError(msg) {
    authMessage.textContent = msg;
    authMessage.style.color = 'red';
}

// --- DASHBOARD TAB SWITCHING ---

function switchDashTab(tab) {
    const uploadTab = document.getElementById('upload-tab');
    const sitesTab = document.getElementById('sites-tab');
    const buttons = document.querySelectorAll('.dash-tab-btn');

    if (!uploadTab || !sitesTab) {
        console.error('Dashboard tabs not found');
        return;
    }

    if (tab === 'upload') {
        uploadTab.classList.remove('hidden');
        sitesTab.classList.add('hidden');
        buttons[0].classList.add('active');
        buttons[1].classList.remove('active');
    } else if (tab === 'sites') {
        uploadTab.classList.add('hidden');
        sitesTab.classList.remove('hidden');
        buttons[0].classList.remove('active');
        buttons[1].classList.add('active');
        loadSites();
    }
}

// --- SITES MANAGEMENT ---

async function loadSites() {
    const sitesList = document.getElementById('sites-list');
    if (!sitesList) return;
    
    sitesList.innerHTML = '<p class="loading">Loading sites...</p>';

    try {
        const res = await fetch(`${API_BASE_URL}/api/deploy`, {
            method: 'GET',
            credentials: 'include'
        });

        if (res.ok) {
            const data = await res.json();
            displaySites(data.sites);
        } else {
            sitesList.innerHTML = '<p class="error">Failed to load sites</p>';
        }
    } catch (err) {
        console.error('Error loading sites:', err);
        sitesList.innerHTML = '<p class="error">Unable to load sites. Please try again.</p>';
    }
}

function displaySites(sites) {
    const sitesList = document.getElementById('sites-list');
    
    if (!sites || sites.length === 0) {
        sitesList.innerHTML = '<p class="empty-state">No sites deployed yet. Upload your first site!</p>';
        return;
    }

    let html = '<div class="sites-grid">';
    
    sites.forEach(site => {
        const launchDate = new Date(site.launch_time).toLocaleDateString();
        const launchTime = new Date(site.launch_time).toLocaleTimeString();
        
        html += `
            <div class="site-card">
                <div class="site-header">
                    <h3>${site.bucket_key}</h3>
                    <span class="status-badge ${site.status.toLowerCase()}">${site.status}</span>
                </div>
                <div class="site-info">
                    <p><strong>Deployed:</strong> ${launchDate} at ${launchTime}</p>
                    <p><strong>URL:</strong> <a href="${site.url}" target="_blank" class="site-link">${site.url}</a></p>
                </div>
                <div class="site-actions">
                    <button onclick="copySiteUrl('${site.url}')" class="btn-small btn-copy">Copy URL</button>
                    <button onclick="deleteSite('${site.bucket_key}')" class="btn-small btn-delete">Delete</button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    sitesList.innerHTML = html;
}

function copySiteUrl(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
            alert('URL copied to clipboard!');
        }).catch(err => {
            console.error('Failed to copy:', err);
            alert('Failed to copy URL');
        });
    } else {
        // Fallback for older browsers
        alert('Copy not supported. Please copy manually: ' + url);
    }
}

async function deleteSite(bucketName) {
    if (!confirm(`Are you sure you want to delete "${bucketName}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/deploy/${bucketName}`, {
            method: 'DELETE',
            credentials: 'include'
        });

        const data = await res.json();

        if (res.ok) {
            alert('Site deleted successfully!');
            loadSites();
        } else {
            alert('Failed to delete site: ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        console.error('Error deleting site:', err);
        alert('Unable to delete site. Please try again.');
    }
}

function refreshSites() {
    loadSites();
}

// --- UPLOAD LOGIC (Drag & Drop) ---
// Note: Ensure your upload route in Python also checks "if 'user_id' in session"

dropZone.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleUpload(e.target.files[0]);
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files[0]);
});

async function handleUpload(file) {
    if (!file.name.endsWith('.zip') && !file.name.endsWith('.html')) {
        alert("Only .zip or .html files are allowed!");
        return;
    }

    const statusBox = document.getElementById('upload-status');
    const statusText = document.getElementById('status-text');
    const resultLink = document.getElementById('result-link');
    
    if (!statusBox || !statusText || !resultLink) {
        console.error('Upload UI elements not found');
        return;
    }
    
    statusBox.classList.remove('hidden');
    resultLink.classList.add('hidden');
    statusText.textContent = `Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(`${API_BASE_URL}/api/deploy`, {
            method: 'POST',
            credentials: 'include',
            body: formData
        });

        if (res.ok) {
            const data = await res.json();
            statusText.textContent = "Done!";
            resultLink.classList.remove('hidden');
            
            const link = document.getElementById('deployed-url');
            if (link) {
                link.href = data.site_url;
                link.textContent = data.site_url;
            }
            
            // Refresh sites list if on that tab
            const sitesTab = document.getElementById('sites-tab');
            if (sitesTab && !sitesTab.classList.contains('hidden')) {
                loadSites();
            }
        } else {
            const data = await res.json();
            statusText.textContent = "Upload failed: " + (data.error || "Server rejected the file");
        }
    } catch (err) {
        console.error('Upload error:', err);
        statusText.textContent = "Upload failed. Please check your connection and try again.";
    }
}
