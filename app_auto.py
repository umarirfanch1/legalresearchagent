import streamlit as st
import json
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import cohere

st.set_page_config(page_title="Legal Research Auto-MVP")

# ----------------- Load Secrets -----------------
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]["service_account"]
FOLDER_ID = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
COHERE_API_KEY = st.secrets["COHERE_API_KEY"]

# ----------------- Google Drive Auth -----------------
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(
    json.loads(SERVICE_ACCOUNT_INFO),
    scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=creds)

# ----------------- Cohere Client -----------------
co = cohere.Client(COHERE_API_KEY)

# ----------------- List Files -----------------
results = drive_service.files().list(
    q=f"'{FOLDER_ID}' in parents and trashed=false",
    fields="files(id, name, mimeType)"
).execute()
files = results.get('files', [])

if not files:
    st.write("No files found in the Drive folder.")
else:
    st.write(f"Found {len(files)} files in the folder:")

    for file in files:
        st.write(f"- {file['name']} ({file['id']})")

        # ----------------- Download File -----------------
        request = drive_service.files().get_media(fileId=file['id'])
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        content = fh.getvalue().decode('utf-8', errors='ignore')

        # ----------------- Generate Summary -----------------
        prompt = f"Read the following legal document and generate a detailed, structured strategic summary:\n\n{content}\n\nSummary:"
        response = co.summarize(text=content) if hasattr(co, 'summarize') else co.generate(model='xlarge', prompt=prompt, max_tokens=400)
        summary_text = response if isinstance(response, str) else response.text

        # ----------------- Upload Summary Back -----------------
        summary_filename = f"{file['name']}_SUMMARY.txt"
        fh_summary = BytesIO(summary_text.encode('utf-8'))
        media = MediaFileUpload(summary_filename, mimetype='text/plain', resumable=True)
        file_metadata = {
            'name': summary_filename,
            'parents': [FOLDER_ID]
        }
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        st.success(f"Summary for {file['name']} uploaded as {summary_filename} (ID: {uploaded_file['id']})")
