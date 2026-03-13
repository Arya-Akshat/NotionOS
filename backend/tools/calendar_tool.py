import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_PATH = 'token_calendar.json'
CREDENTIALS_PATH = 'credentials.json'

def get_gcal_service():
    """Returns a Google Calendar service instance. Non-interactive if token exists."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(f"{CREDENTIALS_PATH} not found. Calendar integration requires Google OAuth credentials.")
            
            if os.environ.get("SERVER_MODE") == "true":
                raise PermissionError("Interactive Google Auth required but running in SERVER_MODE. Run manually once to generate token_calendar.json.")

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def list_events(max_results=10):
    try:
        service = get_gcal_service()
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=max_results, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        return {"success": True, "data": events, "error": None}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"CALENDAR_ERROR:{str(e)}"}

def create_event(summary: str, description: str, start_time: str, end_time: str):
    try:
        service = get_gcal_service()
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'UTC',
            },
        }
        
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return {"success": True, "data": created_event, "error": None}
    except Exception as e:
        return {"success": False, "data": {}, "error": f"CALENDAR_ERROR:{str(e)}"}
