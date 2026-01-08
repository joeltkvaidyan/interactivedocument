from flask import Flask, request, render_template, jsonify
import PyPDF2
import pdfplumber
import pdf2image
import pytesseract
import cv2
import numpy as np
from PIL import Image
import os
import traceback
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from Vercel
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# Flask app
app = Flask(__name__, 
            static_folder="../static",
            template_folder="../templates")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB

# Global storage
CURRENT_DOC_TEXT = ""
CURRENT_FILENAME = ""

# ===== PDF TEXT EXTRACTION =====
def is_scanned_pdf(text: str) -> bool:
    return len(text.strip()) < 100

def extract_text_with_ocr(file_storage, pages_to_ocr=5, char_limit=20000) -> str:
    file_storage.seek(0)
    text = ""

    # Method 1: PyPDF2
    try:
        reader = PyPDF2.PdfReader(file_storage)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    except Exception as e:
        print("PyPDF2 error:", e)

    if not is_scanned_pdf(text):
        return text[:char_limit]

    # Method 2: pdfplumber
    file_storage.seek(0)
    try:
        with pdfplumber.open(file_storage) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        print("pdfplumber error:", e)

    if not is_scanned_pdf(text):
        return text[:char_limit]

    # Method 3: OCR for scanned PDFs
    print("PDF appears scanned. Using OCR...")
    file_storage.seek(0)
    try:
        images = pdf2image.convert_from_bytes(
            file_storage.read(),
            dpi=150,
            first_page=0,
            last_page=pages_to_ocr,
        )

        for idx, img in enumerate(images):
            print(f"OCR processing page {idx+1}...")
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            _, img_bin = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            ocr_text = pytesseract.image_to_string(
                Image.fromarray(img_bin), lang="eng"
            )
            text += ocr_text + "\n"
    except Exception as e:
        print("OCR error:", e)

    return text[:char_limit]

# ===== LLM HELPERS =====
def sunny_chat(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
    response = gemini_model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
            top_p=0.9,
        ),
    )
    return response.text.strip()

def summarize_document(text: str):
    doc_text = text[:8000]

    system_prompt = (
        "You are an expert summarizer for long PDF documents. "
        "You must not hallucinate facts not present in the text."
    )

    user_prompt = f"""
Given the following document text, produce THREE summaries in valid JSON.

DOCUMENT:
\"\"\"{doc_text}\"\"\"

Return JSON with EXACTLY these keys:

{{
  "bullets": "- point 1\\n- point 2\\n- point 3\\n- point 4\\n- point 5",
  "detailed": "2-4 paragraphs, 8-12 sentences total, clear and simple.",
  "short": "2-3 sentence high-level overview."
}}

Rules:
- Only use information from the document.
- Do NOT add external knowledge.
- Return ONLY the JSON, no extra text.
"""

    raw = sunny_chat(system_prompt, user_prompt, temperature=0.2)

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            json_str = raw[start:end]
            data = json.loads(json_str)
            return (
                data.get("bullets", ""),
                data.get("detailed", ""),
                data.get("short", ""),
            )
    except Exception as e:
        print("JSON parse error:", e)

    return ("Summary unavailable", raw[:1000], raw[:300])

def answer_question_fulltext(question: str, full_text: str) -> str:
    context = full_text[:12000]

    system_prompt = (
        "You are a precise Q&A assistant for PDF documents. "
        "Answer strictly based on the given document text. "
        "If the answer is not in the text, say exactly: "
        "\"I don't know based on this document.\""
    )

    user_prompt = f"""
DOCUMENT TEXT:
\"\"\"{context}\"\"\"

QUESTION:
{question}

Answer clearly in 2-5 sentences. Do not introduce information not supported by the document.
"""

    return sunny_chat(system_prompt, user_prompt, temperature=0.2)

# ===== ROUTES =====
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    global CURRENT_DOC_TEXT, CURRENT_FILENAME

    try:
        if "pdf" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["pdf"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Please upload a PDF file"}), 400

        print(f"Processing file: {file.filename}")

        text = extract_text_with_ocr(file, pages_to_ocr=5)
        if not text or len(text) < 100:
            return jsonify({"error": "Could not extract usable text from PDF."}), 400

        print(f"✅ Extracted {len(text)} characters")

        CURRENT_DOC_TEXT = text
        CURRENT_FILENAME = file.filename.rsplit(".", 1)[0]

        print("🔍 Generating summaries...")
        bullets, detailed, short = summarize_document(text)
        print("✅ Summarization complete")

        return jsonify(
            {
                "success": True,
                "summary_bullets": bullets,
                "summary_detailed": detailed,
                "summary_short": short,
                "filename": CURRENT_FILENAME,
            }
        )

    except Exception as e:
        print("ERROR in /upload:", traceback.format_exc())
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/ask", methods=["POST"])
def ask_question():
    global CURRENT_DOC_TEXT, CURRENT_FILENAME

    try:
        data = request.json
        question = (data.get("question") or "").strip()
        filename = (data.get("filename") or "").strip()

        if not question:
            return jsonify({"error": "Question is required"}), 400

        if not CURRENT_DOC_TEXT or not CURRENT_FILENAME:
            return jsonify({"error": "No document in memory. Upload again."}), 400

        print(f"Question: {question}")
        answer = answer_question_fulltext(question, CURRENT_DOC_TEXT)

        return jsonify(
            {
                "success": True,
                "answer": answer,
                "filename": CURRENT_FILENAME,
            }
        )

    except Exception as e:
        print("ERROR in /ask:", traceback.format_exc())
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large (max 20MB)."}), 413
