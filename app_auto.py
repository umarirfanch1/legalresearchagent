import json
from io import BytesIO
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# Load config
with open("config.json") as f:
    config = json.load(f)

SERVICE_ACCOUNT_FILE = config["GOOGLE_SERVICE_ACCOUNT_JSON"]
FOLDER_ID = config["GOOGLE_DRIVE_FOLDER_ID"]

# Authenticate Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# List files in folder
results = drive_service.files().list(q=f"'{FOLDER_ID}' in parents and trashed=false").execute()
files = results.get('files', [])

if not files:
    print("No files found in the Drive folder.")
else:
    print(f"Found {len(files)} files in the folder:")
    for file in files:
        print(f"- {file['name']} (ID: {file['id']})")

        # Download content to verify
        request = drive_service.files().get_media(fileId=file['id'])
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        content = fh.getvalue().decode('utf-8')
        print(f"Preview (first 500 chars):\n{content[:500]}\n{'-'*50}")
