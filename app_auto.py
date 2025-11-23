import streamlit as st
import json
from io import BytesIO

from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

import cohere

st.set_page_config(page_title="Legal Research MVP Auto-Fetch")
st.title("📄 Legal Research MVP: Google Drive Auto-Fetch & AI Summary")

# =========================================================
# 1. LOAD SECRETS
# =========================================================
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
INPUT_FOLDER_ID = st.secrets["drive"]["input_folder_id"]
OUTPUT_FOLDER_ID = st.secrets["drive"]["output_folder_id"]
COHERE_API_KEY = st.secrets["cohere"]["api_key"]

# =========================================================
# 2. GOOGLE DRIVE AUTHENTICATION
# =========================================================
SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=creds)

# =========================================================
# 3. COHERE CLIENT
# =========================================================
co = cohere.Client(COHERE_API_KEY)

st.success("Connected to Google Drive & Cohere ✔️")

# =========================================================
# 4. LIST FILES IN INPUT FOLDER
# =========================================================
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

# =========================================================
# 5. PROCESS EACH FILE
# =========================================================
for file in files:

    st.subheader(f"📌 Processing: {file['name']}")

    # ---------------------- DOWNLOAD ----------------------
    try:
        if file["mimeType"] == "application/vnd.google-apps.document":
            request = drive_service.files().export_media(
                fileId=file["id"], 
                mimeType="text/plain"
            )
        else:
            request = drive_service.files().get_media(fileId=file["id"])

        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        try:
            content = fh.getvalue().decode("utf-8")
        except UnicodeDecodeError:
            content = "(Binary file — skipping preview)"

        st.code(content[:500], language="text")

    except HttpError as e:
        st.error(f"❌ Download failed for {file['name']}: {e}")
        continue

    # ---------------------- SUMMARY ----------------------
    summary = ""
    if "Binary file" not in content and content.strip():
        prompt = f"Summarize this legal document clearly and concisely:\n\n{content}"

        try:
            response = co.chat(
                model="command-xlarge-nightly",
                message=prompt
            )

            # Correct field for Cohere Chat
            summary = response.text  

            st.write("### 🧠 AI Summary")
            st.text(summary)

        except Exception as e:
            st.error(f"❌ AI summary generation failed: {e}")
            summary = ""

    # Skip saving if no summary
    if not summary.strip():
        st.warning("⚠️ No summary generated — skipping upload.")
        continue

    # ---------------------- SAVE SUMMARY ----------------------
    summary_filename = f"{file['name']}_summary.txt"
    summary_bytes = BytesIO(summary.encode("utf-8"))

    media = MediaIoBaseUpload(summary_bytes, mimetype="text/plain", resumable=True)
    file_metadata = {"name": summary_filename, "parents": [OUTPUT_FOLDER_ID]}

    try:
        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True
        ).execute()

        st.success(f"✔️ Summary saved to Drive as **{summary_filename}**")

    except HttpError as e:
        st.error(f"❌ Failed to save summary: {e}")

st.info("🎉 All files processed.")
