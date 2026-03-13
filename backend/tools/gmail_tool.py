import os
import base64
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'token_gmail.json'
CREDENTIALS_PATH = 'credentials.json'

def get_gmail_service():
    """Returns a Gmail service instance. Non-interactive if token exists."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(f"{CREDENTIALS_PATH} not found. Gmail integration requires Google OAuth credentials.")
            
            # This part still requires interactive auth if no token exists.
            # In server mode, we fail early with a clear message.
            if os.environ.get("SERVER_MODE") == "true":
                raise PermissionError("Interactive Google Auth required but running in SERVER_MODE. Run manually once to generate token_gmail.json.")
                
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def send_email(to: str, subject: str, body: str):
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        send_message = service.users().messages().send(
            userId="me", body=create_message).execute()
            
        return {"success": True, "data": send_message, "error": None}
    except Exception as error:
        return {"success": False, "data": {}, "error": f"GMAIL_ERROR:{str(error)}"}

def read_emails(max_results=10):
    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', maxResults=max_results).execute()
        messages = results.get('messages', [])
        return {"success": True, "data": messages, "error": None}
    except Exception as error:
         return {"success": False, "data": {}, "error": f"GMAIL_ERROR:{str(error)}"}
