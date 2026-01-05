#OPENROUTER_API_KEY = "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"
import io
import uuid
import httpx
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from docx import Document
from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 DIRECT API KEY (Windows-safe)
OPENROUTER_API_KEY = "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"

# ✅ STABLE FREE MODEL
MODEL_NAME = "mistralai/mistral-7b-instruct:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# In-memory session storage
sessions = {}

@app.get("/")
async def home():
    return FileResponse("static/index.html")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    contents = await file.read()
    filename = file.filename.lower()
    extracted_text = ""

    try:
        if filename.endswith(".pdf"):
            try:
                reader = PdfReader(io.BytesIO(contents))
                extracted_text = "".join(p.extract_text() or "" for p in reader.pages)
            except:
                pages = convert_from_bytes(contents)
                extracted_text = "\n".join(
                    pytesseract.image_to_string(p) for p in pages
                )

        elif filename.endswith(".txt"):
            extracted_text = contents.decode()

        elif filename.endswith(".docx"):
            doc = Document(io.BytesIO(contents))
            extracted_text = "\n".join(p.text for p in doc.paragraphs)

        elif filename.endswith((".png", ".jpg", ".jpeg")):
            image = Image.open(io.BytesIO(contents))
            extracted_text = pytesseract.image_to_string(image)

        else:
            return JSONResponse({"error": "Unsupported file type"}, status_code=400)

        # 🔒 limit context size (prevents 400 errors)
        sessions[session_id] = {
            "text": extracted_text[:6000],
            "history": []
        }

        return {
            "session_id": session_id,
            "message": "File uploaded successfully"
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/ask")
async def ask_question(
    session_id: str = Form(...),
    question: str = Form(...)
):
    if session_id not in sessions:
        return JSONResponse({"error": "Invalid session"}, status_code=400)

    session = sessions[session_id]
    session["history"].append({"role": "user", "content": question})

    messages = [
        {
            "role": "system",
            "content": (
                "Answer only using the document content. "
                "If not found, say: Not found in file.\n\n"
                + session["text"]
            )
        }
    ] + session["history"]

    payload = {
        "model": MODEL_NAME,
        "messages": messages
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)

    if resp.status_code != 200:
        return JSONResponse(
            {
                "error": "LLM request failed",
                "status": resp.status_code,
                "details": resp.text
            },
            status_code=500
        )

    answer = resp.json()["choices"][0]["message"]["content"]
    session["history"].append({"role": "assistant", "content": answer})

    return {"answer": answer}

@app.post("/reset")
async def reset_chat(session_id: str = Form(...)):
    if session_id in sessions:
        sessions[session_id]["history"] = []
    return {"message": "Chat reset successful"}
