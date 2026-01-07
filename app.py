# ===== IMPORTS =====
# These bring in libraries we need for our project
from flask import Flask, request, render_template, jsonify, send_from_directory
import PyPDF2
import pdfplumber
import pdf2image
import pytesseract
import cv2
import numpy as np
from PIL import Image
from transformers import pipeline
import torch
from io import BytesIO
import os
import traceback

# ===== FLASK APP SETUP =====
# Create the Flask application (this becomes our website)
app = Flask(__name__)

# Configure max file size (20MB max for PDF uploads)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024

# ===== LOAD AI MODELS (Happens once when app starts) =====
print("Loading AI models... This takes 30 seconds first time. Please wait.")

# Summarization model: Takes long text → short summary
# t5-small: Small, fast, free (250MB download)
summarizer = pipeline("summarization", model="t5-small")

# Question-Answering model: Answer questions about the document
# distilbert: Fast, accurate, good for student projects
qa_pipeline = pipeline("question-answering", model="distilbert-base-cased-distilled-squad")

print("✅ Models loaded successfully!")

# ===== HELPER FUNCTIONS =====

def is_scanned_pdf(text):
    """
    Check if PDF is scanned (image-based) or normal (text-based)
    
    Why: Some PDFs are just images - we need OCR for those
    How: If extracted text is very small, it's likely scanned
    """
    return len(text.strip()) < 100

def extract_text_with_ocr(file_storage, pages_to_ocr=3):
    """
    Extract text from PDF using three methods:
    1. Try PyPDF2 first (fast, for normal PDFs)
    2. Try pdfplumber (better accuracy)
    3. Use Tesseract OCR (for scanned PDFs with images)
    
    Args:
        file_storage: PDF file from user upload
        pages_to_ocr: How many pages to OCR (limit for speed)
    
    Returns:
        Extracted text string
    """
    
    # Reset file pointer to beginning
    file_storage.seek(0)
    text = ""
    
    # METHOD 1: Try PyPDF2 (fastest)
    try:
        pdf_reader = PyPDF2.PdfReader(file_storage)
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except:
        pass
    
    # If we got good text, return it (no OCR needed)
    if not is_scanned_pdf(text):
        return text[:6000]  # Limit to 6000 chars for faster processing
    
    # METHOD 2: Try pdfplumber (better for complex PDFs)
    file_storage.seek(0)
    try:
        with pdfplumber.open(file_storage) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except:
        pass
    
    if not is_scanned_pdf(text):
        return text[:6000]
    
    # METHOD 3: Use OCR for scanned PDFs (slower but works!)
    print("PDF is scanned - using OCR. This may take 30-60 seconds...")
    file_storage.seek(0)
    
    try:
        # Convert PDF pages to images
        # dpi=150: Image quality (higher = better but slower)
        # first_page=0, last_page: Which pages to OCR
        images = pdf2image.convert_from_bytes(
            file_storage.read(),
            dpi=150,
            first_page=0,
            last_page=pages_to_ocr
        )
        
        for img in images:
            # Preprocess image for better OCR accuracy
            # Step 1: Convert to grayscale (black & white)
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            
            # Step 2: Apply threshold (make text darker, background lighter)
            # OTSU method automatically finds best threshold
            _, img_bin = cv2.threshold(
                img_cv, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            
            # Step 3: Run Tesseract OCR
            # lang='eng': English language
            ocr_text = pytesseract.image_to_string(
                Image.fromarray(img_bin),
                lang='eng'
            )
            text += ocr_text + "\n"
    
    except Exception as e:
        return f"Error during OCR: {str(e)}"
    
    return text[:6000]

def summarize_text(text):
    """
    Summarize long text into key points
    
    How it works:
    1. Split text into chunks (model has a limit of ~1000 chars)
    2. Summarize each chunk
    3. Combine summaries and summarize again (map-reduce)
    
    Parameters explained:
    - max_length=150: Summary should be max 150 words
    - min_length=30: Summary should be at least 30 words
    - do_sample=False: Always pick best summary (no randomness)
    """
    
    # If text is too short, just use it as-is
    if len(text) < 200:
        return text
    
    # Split into chunks (each ~1000 chars)
    chunk_size = 1000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    # Summarize each chunk
    chunk_summaries = []
    for chunk in chunks:
        if len(chunk) > 50:  # Only summarize if chunk has content
            try:
                summary = summarizer(
                    chunk,
                    max_length=150,
                    min_length=30,
                    do_sample=False
                )['summary_text']
                chunk_summaries.append(summary)
            except:
                chunk_summaries.append(chunk[:200])  # Fallback
    
    # Combine summaries
    combined = " ".join(chunk_summaries)
    
    # Final summary of summaries
    if len(combined) > 200:
        try:
            final_summary = summarizer(
                combined,
                max_length=200,
                min_length=50,
                do_sample=False
            )['summary_text']
            return final_summary
        except:
            return combined[:500]
    
    return combined

# ===== FLASK ROUTES (Website pages) =====

@app.route('/')
def home():
    """
    Home page - shows upload form
    render_template: Loads index.html from templates folder
    """
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handle file upload and return summary
    
    POST data: The PDF file user uploads
    Returns: JSON with summary and full text
    """
    
    try:
        # Check if file was uploaded
        if 'pdf' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['pdf']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.pdf'):
            return jsonify({'error': 'Please upload a PDF file'}), 400
        
        print(f"Processing file: {file.filename}")
        
        # Extract text from PDF
        full_text = extract_text_with_ocr(file, pages_to_ocr=5)
        
        if not full_text or len(full_text) < 50:
            return jsonify({'error': 'Could not extract text from PDF. Try a different file.'}), 400
        
        # Generate summary
        print("Generating summary...")
        summary = summarize_text(full_text)
        
        # Return both summary and full text (for Q&A)
        return jsonify({
            'summary': summary,
            'full_text': full_text[:4000],  # Limit for display
            'success': True
        })
    
    except Exception as e:
        print(f"Error: {traceback.format_exc()}")
        return jsonify({'error': f'Processing error: {str(e)}'}), 500

@app.route('/ask', methods=['POST'])
def ask_question():
    """
    Answer questions about the document
    
    POST data: 
        - question: What user asks
        - context: The document text
    
    Returns: JSON with answer
    """
    
    try:
        data = request.json
        question = data.get('question', '').strip()
        context = data.get('context', '').strip()
        
        if not question or not context:
            return jsonify({'error': 'Question and context required'}), 400
        
        # Limit context to 2000 chars (model limit)
        context = context[:2000]
        
        print(f"Question: {question}")
        
        # Use Q&A model to answer
        try:
            result = qa_pipeline(
                question=question,
                context=context
            )
            answer = result['answer']
            confidence = round(result['score'] * 100, 1)
            
            # If confidence is low, suggest to user
            if confidence < 50:
                answer = f"Not sure, but possible answer: {answer} (confidence: {confidence}%)"
            
            return jsonify({
                'answer': answer,
                'confidence': confidence,
                'success': True
            })
        
        except Exception as e:
            return jsonify({'error': f'Could not answer: {str(e)}'}), 500
    
    except Exception as e:
        print(f"Error: {traceback.format_exc()}")
        return jsonify({'error': 'Server error'}), 500

@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({'error': 'File too large (max 20MB)'}), 413

@app.errorhandler(500)
def server_error(e):
    """Handle server errors gracefully"""
    return jsonify({'error': 'Server error occurred'}), 500

# ===== RUN THE APP =====
if __name__ == '__main__':
    # debug=True: Auto-reload when code changes (for development)
    # port=5000: Website runs at http://localhost:5000
    app.run(debug=True, port=5000)
