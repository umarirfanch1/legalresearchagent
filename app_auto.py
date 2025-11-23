import streamlit as st
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

st.title("Google Drive MVP Auto-Fetch")

# --- Load secrets from Streamlit ---
try:
    service_info = st.secrets["gcp_service_account"]   # JSON key stored inside Streamlit
    folder_id = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
except KeyError as e:
    st.error(f"Missing Streamlit secret: {e}")
    st.stop()

# --- Authenticate Google Service Account ---
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
creds = service_account.Credentials.from_service_account_info(
    service_info, scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=creds)

st.write("✅ Google Drive authenticated successfully")

# --- List files inside the Drive folder ---
try:
    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed=false"
    ).execute()
    files = results.get("files", [])
except Exception as e:
    st.error(f"Error listing files: {e}")
    st.stop()

if not files:
    st.warning("No files found in this Drive folder.")
else:
    st.success(f"Found **{len(files)}** files:")

    for file in files:
        file_id = file["id"]
        file_name = file["name"]

        st.write(f"### 📄 {file_name}")
        st.caption(f"File ID: `{file_id}`")

        # --- Download the file content ---
        try:
            request = drive_service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            content = fh.getvalue().decode("utf-8")

            st.text_area(
                f"Preview: {file_name}",
                content[:1000],
                height=200
            )

        except Exception as e:
            st.error(f"Error downloading {file_name}: {e}")
