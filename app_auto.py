import streamlit as st
import json
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError
import cohere

st.set_page_config(page_title="Legal Research MVP Auto-Fetch")
st.title("Legal Research MVP: Google Drive Auto-Fetch & Summary")

# ----------------- Load Secrets -----------------
SERVICE_ACCOUNT_INFO = json.loads(st.secrets["gcp_service_account"]["service_account"])
FOLDER_ID = st.secrets["drive"]["folder_id"]
COHERE_API_KEY = st.secrets["cohere"]["api_key"]

# ----------------- Authenticate Google Drive -----------------
SCOPES = ["https://www.googleapis.com/auth/drive"]
creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)

# ----------------- Initialize Cohere -----------------
co = cohere.Client(COHERE_API_KEY)

st.write("✅ Authenticated with Google Drive and Cohere.")

# ----------------- List Files in Drive Folder -----------------
try:
    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()
except HttpError as e:
    st.error(f"Failed to list files in the Drive folder: {e}")
    st.stop()

files = results.get("files", [])

if not files:
    st.warning("No files found in the Drive folder.")
else:
    st.success(f"Found {len(files)} files in the folder:")

    for file in files:
        st.write(f"- {file['name']} ({file['id']})")

        # ----------------- Download File Content -----------------
        try:
            if file["mimeType"] == "application/vnd.google-apps.document":
                request = drive_service.files().export_media(fileId=file["id"], mimeType="text/plain")
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
                content = "(Binary / non-text file, skipping preview)"

            st.code(content[:500], language="text")

            # ----------------- Generate AI Summary -----------------
            if content.strip() != "" and "Binary / non-text" not in content:
                prompt = f"Summarize this legal case in structured points:\n\n{content}"
                try:
                    response = co.generate(
                        model="command-xlarge-nightly",  # Valid Cohere model
                        prompt=prompt,
                        max_tokens=300
                    )
                    summary = response.generations[0].text
                    st.write("**AI Summary:**")
                    st.text(summary)
                except Exception as e:
                    st.error(f"AI summary generation failed: {e}")
                    summary = "(Failed to generate summary)"

                # ----------------- Save Summary Back to Drive -----------------
                summary_filename = f"{file['name']}_summary.txt"
                summary_bytes = BytesIO(summary.encode("utf-8"))
                file_metadata = {"name": summary_filename, "parents": [FOLDER_ID]}
                try:
                    drive_service.files().create(
                        body=file_metadata,
                        media_body=MediaFileUpload(summary_filename, mimetype="text/plain", resumable=True),
                        fields="id"
                    ).execute()
                    st.success(f"Summary saved as {summary_filename} in the same Drive folder.")
                except HttpError as e:
                    st.error(f"Failed to save summary for {file['name']}: {e}")

        except HttpError as e:
            st.error(f"Failed to download file {file['name']}: {e}")

st.info("✅ Done processing all files.")
