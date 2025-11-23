import streamlit as st
import json
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import cohere
from docx import Document
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import datetime
import urllib.parse

st.set_page_config(page_title="Legal Research MVP Auto-Fetch Webhook")
st.title("Legal Research MVP Webhook Receiver")

# ----------------- Load Secrets -----------------
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
INPUT_FOLDER_ID = st.secrets["drive"]["input_folder_id"]
COHERE_API_KEY = st.secrets["cohere"]["api_key"]

# Gmail config
SENDER_EMAIL = st.secrets["gmail"]["sender_email"]
SENDER_PASSWORD = st.secrets["gmail"]["sender_password"]
RECEIVER_EMAIL = st.secrets["gmail"]["receiver_email"]

# ----------------- Authenticate Google Drive -----------------
SCOPES = ["https://www.googleapis.com/auth/drive"]
creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)

# ----------------- Initialize Cohere -----------------
co = cohere.Client(COHERE_API_KEY)

# ----------------- Helper Functions -----------------
def extract_docx_text(fh):
    try:
        fh.seek(0)
        doc = Document(fh)
        full_text = [para.text for para in doc.paragraphs]
        return "\n".join(full_text)
    except Exception:
        return "(Could not read Word file)"

def generate_pdf(file_name, summary_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 8, summary_text)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    pdf_bytes = BytesIO()
    pdf.output(pdf_bytes)
    pdf_bytes.seek(0)
    return f"{file_name}_summary_{timestamp}.pdf", pdf_bytes

def send_email(sender, password, receiver, subject, body_text, pdf_bytes, pdf_filename):
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))
    part = MIMEApplication(pdf_bytes.read(), Name=pdf_filename)
    part['Content-Disposition'] = f'attachment; filename="{pdf_filename}"'
    msg.attach(part)
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender, password)
    server.send_message(msg)
    server.quit()

# ----------------- Webhook Receiver -----------------
st.write("Ready to process uploaded file.")

# Get file_id from query params for webhook
params = st.experimental_get_query_params()
file_id = params.get("file_id", [None])[0]

# For testing, also allow manual input
file_id_input = st.text_input("Enter file ID to test manually")
if file_id_input:
    file_id = file_id_input

if file_id:
    try:
        file = drive_service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        file_name = file["name"]
        mime_type = file["mimeType"]

        # Download file
        fh = BytesIO()
        if mime_type == "application/vnd.google-apps.document":
            request = drive_service.files().export_media(fileId=file_id, mimeType="text/plain")
        else:
            request = drive_service.files().get_media(fileId=file_id)

        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        # Extract content
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            content = extract_docx_text(fh)
        else:
            try:
                content = fh.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                content = "(Binary / non-text file)"

        st.code(content[:500], language="text")

        # ----------------- Generate AI Summary -----------------
        summary = "(Failed to generate summary)"
        if content.strip() != "" and "Binary / non-text" not in content:
            prompt = f"Summarize this legal document in structured points:\n\n{content}"
            try:
                response = co.generate(model="xlarge", prompt=prompt, max_tokens=300)
                summary = response.generations[0].text
            except Exception as e:
                st.error(f"AI summary generation failed: {e}")

        st.write("**AI Summary:**")
        st.text(summary)

        # ----------------- Generate PDF -----------------
        pdf_filename, pdf_bytes = generate_pdf(file_name, summary)

        # ----------------- Send Email -----------------
        send_email(
            sender=SENDER_EMAIL,
            password=SENDER_PASSWORD,
            receiver=RECEIVER_EMAIL,
            subject=f"AI Summary for {file_name}",
            body_text="Attached is the AI-generated summary PDF.",
            pdf_bytes=pdf_bytes,
            pdf_filename=pdf_filename
        )
        st.success(f"PDF summary sent to {RECEIVER_EMAIL}: {pdf_filename}")

    except HttpError as e:
        st.error(f"Google Drive error: {e}")
    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("No file ID received yet.")
