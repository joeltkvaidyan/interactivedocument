// ===== DOM ELEMENTS (References to HTML elements) =====
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileNameDisplay = document.getElementById('fileName');
const submitBtn = document.getElementById('submitBtn');
const loader = document.getElementById('loader');
const errorDiv = document.getElementById('error');

// ===== DRAG AND DROP FUNCTIONALITY =====

// When user hovers over upload area
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.style.backgroundColor = 'rgba(37, 99, 235, 0.15)';
});

// When user leaves upload area
uploadArea.addEventListener('dragleave', () => {
    uploadArea.style.backgroundColor = 'rgba(37, 99, 235, 0.05)';
});

// When user drops file
uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.style.backgroundColor = 'rgba(37, 99, 235, 0.05)';
    
    // Get dropped files
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;  // Set as selected file
        handleFileSelect();
    }
});

// When user clicks to select file
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

// When file is selected (click or drag)
fileInput.addEventListener('change', handleFileSelect);

// ===== HANDLE FILE SELECTION =====
function handleFileSelect() {
    const file = fileInput.files;
    
    // Validate file
    if (!file) return;
    
    if (file.type !== 'application/pdf') {
        showError('❌ Please upload a PDF file');
        return;
    }
    
    const maxSize = 20 * 1024 * 1024;  // 20MB
    if (file.size > maxSize) {
        showError('❌ File too large. Maximum 20MB allowed.');
        return;
    }
    
    // Show file name
    fileNameDisplay.textContent = `✅ Selected: ${file.name}`;
    fileNameDisplay.style.display = 'block';
    submitBtn.style.display = 'block';
    errorDiv.style.display = 'none';
}

// ===== SUBMIT BUTTON HANDLER =====
submitBtn.addEventListener('click', uploadFile);

async function uploadFile() {
    const file = fileInput.files;
    if (!file) return;
    
    // Create FormData (special format for sending files)
    const formData = new FormData();
    formData.append('pdf', file);
    
    // Show loading spinner
    loader.style.display = 'block';
    submitBtn.style.display = 'none';
    errorDiv.style.display = 'none';
    
    try {
        // Send file to backend (/upload endpoint)
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        // Parse response as JSON
        const data = await response.json();
        
        if (data.success) {
            // Success! Save data and redirect to results page
            sessionStorage.setItem('summary', data.summary);
            sessionStorage.setItem('fullText', data.full_text);
            
            // Redirect to results page
            window.location.href = '/results';
        } else {
            showError(`❌ ${data.error}`);
            loader.style.display = 'none';
            submitBtn.style.display = 'block';
        }
    } catch (error) {
        showError(`❌ Error: ${error.message}`);
        loader.style.display = 'none';
        submitBtn.style.display = 'block';
    }
}

// ===== RESULTS PAGE LOGIC =====

// When page loads, check if we have summary data
window.addEventListener('DOMContentLoaded', () => {
    const summary = sessionStorage.getItem('summary');
    const fullText = sessionStorage.getItem('fullText');
    
    if (summary && document.getElementById('summary')) {
        // We're on results page - display summary
        document.getElementById('summary').textContent = summary;
        document.getElementById('preview').textContent = fullText;
        
        // Clear session storage
        sessionStorage.removeItem('summary');
        sessionStorage.removeItem('fullText');
    }
});

// ===== QUESTION ANSWERING =====

async function askQuestion() {
    const questionInput = document.getElementById('questionInput');
    const question = questionInput.value.trim();
    const fullText = document.getElementById('preview').textContent;
    
    if (!question) {
        alert('Please ask a question');
        return;
    }
    
    // Show loading
    document.getElementById('qaLoader').style.display = 'block';
    document.getElementById('qaError').style.display = 'none';
    
    try {
        // Send question to backend (/ask endpoint)
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                question: question,
                context: fullText
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Display Q&A in chat
            const chatMessages = document.getElementById('chatMessages');
            
            // Add question
            const qDiv = document.createElement('div');
            qDiv.className = 'chat-message message-question';
            qDiv.innerHTML = `
                <div class="message-label">❓ Your Question:</div>
                <div class="message-text">${question}</div>
            `;
            chatMessages.appendChild(qDiv);
            
            // Add answer
            const aDiv = document.createElement('div');
            aDiv.className = 'chat-message message-answer';
            aDiv.innerHTML = `
                <div class="message-label">✅ Answer (Confidence: ${data.confidence}%):</div>
                <div class="message-text">${data.answer}</div>
            `;
            chatMessages.appendChild(aDiv);
            
            // Scroll to latest message
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Clear input
            questionInput.value = '';
        } else {
            showQAError(`❌ ${data.error}`);
        }
    } catch (error) {
        showQAError(`❌ Error: ${error.message}`);
    } finally {
        document.getElementById('qaLoader').style.display = 'none';
    }
}

// Enter key to submit
document.addEventListener('DOMContentLoaded', () => {
    const questionInput = document.getElementById('questionInput');
    if (questionInput) {
        questionInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                askQuestion();
            }
        });
    }
});

// ===== ERROR DISPLAY FUNCTIONS =====

function showError(message) {
    const errorDiv = document.getElementById('error');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }
}

function showQAError(message) {
    const qaError = document.getElementById('qaError');
    if (qaError) {
        qaError.textContent = message;
        qaError.style.display = 'block';
    }
}
