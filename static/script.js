let currentFilename = '';
let lastBullets = '';
let lastDetailed = '';
let lastShort = '';

// DOM elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileNameDisplay = document.getElementById('fileName');
const submitBtn = document.getElementById('submitBtn');
const loader = document.getElementById('loader');
const errorDiv = document.getElementById('error');

const summarySection = document.getElementById('summarySection');
const summaryTitle = document.getElementById('summaryTitle');
const summaryContent = document.getElementById('summaryContent');
const summaryModeSelect = document.getElementById('summaryMode');

const chatMessages = document.getElementById('chatMessages');
const qaLoader = document.getElementById('qaLoader');
const qaError = document.getElementById('qaError');
const questionInput = document.getElementById('questionInput');
const askBtn = document.getElementById('askBtn');

// ===== File Upload Handling =====
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('upload-area-hover');
});
uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('upload-area-hover');
});
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('upload-area-hover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        handleFileSelect();
    }
});
uploadArea.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFileSelect);

function handleFileSelect() {
    const file = fileInput.files[0];
    if (!file) return;

    if (file.type !== 'application/pdf') {
        showError('❌ Please upload a PDF file');
        return;
    }
    const maxSize = 20 * 1024 * 1024;
    if (file.size > maxSize) {
        showError('❌ File too large (max 20MB)');
        return;
    }

    fileNameDisplay.textContent = `✅ Selected: ${file.name}`;
    fileNameDisplay.style.display = 'block';
    submitBtn.style.display = 'inline-block';
    errorDiv.style.display = 'none';
    summarySection.style.display = 'none';

    // Clear previous state
    lastBullets = '';
    lastDetailed = '';
    lastShort = '';
    currentFilename = '';
    summaryContent.textContent = '';
}

submitBtn.addEventListener('click', uploadFile);

async function uploadFile() {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('pdf', file);

    loader.style.display = 'block';
    submitBtn.style.display = 'none';
    errorDiv.style.display = 'none';

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.success) {
            currentFilename = data.filename || '';

            lastBullets = data.summary_bullets || '';
            lastDetailed = data.summary_detailed || '';
            lastShort = data.summary_short || '';

            // Show the initial summary based on dropdown
            showSelectedSummary();

            summarySection.style.display = 'block';
        } else {
            showError('❌ ' + (data.error || 'Unknown error'));
            submitBtn.style.display = 'inline-block';
        }
    } catch (err) {
        showError('❌ Error: ' + err.message);
        submitBtn.style.display = 'inline-block';
    } finally {
        loader.style.display = 'none';
    }
}

// ===== Summary Mode Handling =====
summaryModeSelect.addEventListener('change', showSelectedSummary);

function showSelectedSummary() {
    const mode = summaryModeSelect.value;
    let text = '';
    let title = '';

    if (mode === 'bullets') {
        text = lastBullets || 'No bullet summary available.';
        title = '• Bullet Point Summary';
    } else if (mode === 'short') {
        text = lastShort || 'No short overview available.';
        title = '🔎 Short Overview';
    } else {
        text = lastDetailed || 'No detailed overview available.';
        title = '📄 Detailed Overview';
    }

    summaryTitle.textContent = title;
    summaryContent.textContent = text;

    // Optional: highlight current tab buttons if you use them
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.dataset.mode === mode) {
            btn.classList.add('tab-btn-active');
        } else {
            btn.classList.remove('tab-btn-active');
        }
    });
}

// Tab buttons (bottom of summary section)
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        summaryModeSelect.value = mode;
        showSelectedSummary();
    });
});

// ===== Chat QA Handling =====
askBtn.addEventListener('click', askQuestion);
questionInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        askQuestion();
    }
});

async function askQuestion() {
    const question = questionInput.value.trim();
    if (!currentFilename) {
        alert('Please upload a PDF and generate a summary first.');
        return;
    }
    if (!question) {
        alert('Please type a question.');
        return;
    }

    qaLoader.style.display = 'block';
    qaError.style.display = 'none';

    // Add user message to chat
    addChatMessage('user', question);

    try {
        const res = await fetch('/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                question: question,
                filename: currentFilename
            })
        });
        const data = await res.json();

        if (data.success) {
            addChatMessage('assistant', data.answer || 'No answer returned.');
            questionInput.value = '';
        } else {
            showQAError('❌ ' + (data.error || 'Unknown error'));
        }
    } catch (err) {
        showQAError('❌ Error: ' + err.message);
    } finally {
        qaLoader.style.display = 'none';
    }
}

function addChatMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('chat-message');
    msgDiv.classList.add(role === 'user' ? 'message-question' : 'message-answer');

    const label = document.createElement('div');
    label.classList.add('message-label');
    label.textContent = role === 'user' ? '🧑 You' : '🤖 sunny';

    const body = document.createElement('div');
    body.classList.add('message-text');
    body.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');

    msgDiv.appendChild(label);
    msgDiv.appendChild(body);
    chatMessages.appendChild(msgDiv);

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ===== Helpers =====
function showError(message) {
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function showQAError(message) {
    qaError.textContent = message;
    qaError.style.display = 'block';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
