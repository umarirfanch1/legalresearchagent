import streamlit as st
from io import BytesIO
import cohere
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# =========================
# 1. Page Config
# =========================
st.set_page_config(page_title="Legal Research MVP Auto-Fetch")
st.title("📄 Legal Research MVP: Auto-Fetch & AI PDF Summaries")

# =========================
# 2. Load Secrets
# =========================
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
INPUT_FOLDER_ID = st.secrets["drive"]["input_folder_id"]
COHERE_API_KEY = st.secrets["cohere"]["api_key"]
EMAIL_SENDER = st.secrets["email"]["sender_email"]
EMAIL_APP_PASSWORD = st.secrets["email"]["app_password"]
EMAIL_RECIPIENT = st.secrets["email"]["recipient_email"]

# =========================
# 3. Authenticate Google Drive
# =========================
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)
drive_service = build("drive", "v3", credentials=creds)

# =========================
# 4. Initialize Cohere
# =========================
co = cohere.Client(COHERE_API_KEY)
st.success("Connected to Google Drive & Cohere ✔️")

# =========================
# 5. List Files in Input Folder
# =========================
try:
    results = drive_service.files().list(
        q=f"'{INPUT_FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
except HttpError as e:
    st.error(f"Error fetching file list: {e}")
    st.stop()

files = results.get("files", [])
if not files:
    st.warning("⚠️ No files found in the input folder.")
    st.stop()

st.write(f"### Found {len(files)} file(s):")
for f in files:
    st.write(f"• **{f['name']}** ({f['id']})")

st.write("---")

# =========================
# 6. PDF Generation
# =========================
def create_pdf(summary_text, filename):
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=letter)
    width, height = letter
    lines = summary_text.split('\n')
    y = height - 50
    for line in lines:
        c.drawString(50, y, line)
        y -= 15
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer, filename

# =========================
# 7. Email PDF
# =========================
def send_email_pdf(sender_email, sender_app_password, recipient_email, subject, pdf_buffer, pdf_filename):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_buffer.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename={pdf_filename}')
    msg.attach(part)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_app_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# =========================
# 8. Process Each File
# =========================
for file in files:
    st.subheader(f"📌 Processing: {file['name']}")

    # ---------------- Download file
    try:
        if file["mimeType"] == "application/vnd.google-apps.document":
            request = drive_service.files().export_media(fileId=file["id"], mimeType="text/plain")
        else:
            request = drive_service.files().get_media(fileId=file["id"])

        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        try:
            content = fh.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            content = "(Binary / non-text file, skipping preview)"

        st.code(content[:500], language="text")

    except HttpError as e:
        st.error(f"❌ Download failed for {file['name']}: {e}")
        continue

    # ---------------- AI Summary
    summary = ""
    if "Binary / non-text" not in content and content.strip():
        prompt = f"Summarize this legal document clearly and concisely:\n\n{content}"
        try:
            response = co.chat(
                model="command-xlarge-nightly",
                message=prompt
            )
            summary = response.text
            st.write("### 🧠 AI Summary")
            st.text(summary)
        except Exception as e:
            st.error(f"❌ AI summary generation failed: {e}")
            summary = ""

    # ---------------- Create PDF & Email
    if summary.strip():
        pdf_buffer, pdf_filename = create_pdf(summary, f"{file['name']}_summary.pdf")
        email_sent = send_email_pdf(
            sender_email=EMAIL_SENDER,
            sender_app_password=EMAIL_APP_PASSWORD,
            recipient_email=EMAIL_RECIPIENT,
            subject=f"AI PDF Summary: {file['name']}",
            pdf_buffer=pdf_buffer,
            pdf_filename=pdf_filename
        )

        if email_sent:
            st.success(f"✔️ PDF summary emailed for {file['name']}")
        else:
            st.error(f"❌ Failed to send PDF email for {file['name']}")

st.info("🎉 All files processed.")
