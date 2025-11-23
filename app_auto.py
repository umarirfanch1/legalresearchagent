import json
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import streamlit as st
import cohere

# ------------------------
# --- Load secrets -------
# ------------------------
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]["service_account"]
FOLDER_ID = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
COHERE_API_KEY = st.secrets["COHERE_API_KEY"]

# ------------------------
# --- Initialize clients -
# ------------------------
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(
    json.loads(SERVICE_ACCOUNT_INFO), scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=creds)

co = cohere.Client(COHERE_API_KEY)

# ------------------------
# --- List files in Drive -
# ------------------------
results = drive_service.files().list(
    q=f"'{FOLDER_ID}' in parents and trashed=false"
).execute()
files = results.get('files', [])

if not files:
    st.write("No files found in the Drive folder.")
else:
    st.write(f"Found {len(files)} files in the folder:")

# ------------------------
# --- Process each file ---
# ------------------------
for file in files:
    st.write(f"- {file['name']} (ID: {file['id']})")

    # --- Download file ---
    request = drive_service.files().get_media(fileId=file['id'])
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    content = fh.getvalue().decode('utf-8')

    # --- Generate summary using Cohere ---
    st.write("Generating summary...")
    response = co.summarize(
        text=content,
        length="medium",   # short / medium / long
        format="paragraph",
        extractiveness="medium"
    )
    summary = response.summary
    st.write("Summary generated:\n", summary[:500], "...")  # Preview first 500 chars

    # --- Save summary back to Drive ---
    summary_filename = file['name'].replace(".txt", "_summary.txt")
    summary_bytes = summary.encode('utf-8')
    media = MediaFileUpload(filename=None, mimetype='text/plain', resumable=True)
    media._fd = BytesIO(summary_bytes)  # Hack to upload in-memory bytes

    file_metadata = {
        'name': summary_filename,
        'parents': [FOLDER_ID]
    }

    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media
    ).execute()
    st.write(f"Summary saved as: {summary_filename}")
