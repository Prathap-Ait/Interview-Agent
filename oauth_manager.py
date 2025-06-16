import os
import json
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from fastapi import HTTPException

# If modifying these scopes, delete the token.json file.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
REDIRECT_URI = 'http://localhost:3000'  # Must match GCP configuration

class OAuthManager:
    def __init__(self, token_file='token.json', credentials_file='credentials.json'):
        self.token_file = token_file
        self.credentials_file = credentials_file
        self.credentials = None
        self.token_expiry_buffer = 300  # 5 minutes buffer before actual expiry
        
    def get_credentials(self):
        """Get valid user credentials from storage."""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as token:
                    token_data = json.loads(token.read())
                    self.credentials = Credentials.from_authorized_user_info(token_data)
            except (ValueError, KeyError) as e:
                print(f"Error reading token file: {e}")
                self.credentials = None
        
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                return self._refresh_token()
            return self._run_oauth_flow()
            
        return self.credentials
    
    def _is_token_expired_or_expiring_soon(self):
        """Check if the token is expired or will expire soon."""
        if not self.credentials or not self.credentials.expiry:
            return True
            
        expiry_timestamp = self.credentials.expiry.timestamp()
        current_time = time.time()
        return current_time + self.token_expiry_buffer >= expiry_timestamp
    
    def _refresh_token(self):
        """Refresh the access token using refresh token."""
        try:
            print("Refreshing access token...")
            self.credentials.refresh(Request())
            self._save_credentials()
            return self.credentials
        except RefreshError as e:
            print(f"Error refreshing token: {e}")
            return self._run_oauth_flow()
    
    def _run_oauth_flow(self):
        """Run the full OAuth flow to get new credentials."""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_file, 
                SCOPES,
                redirect_uri=REDIRECT_URI
            )
            
            # For local development, use run_local_server
            self.credentials = flow.run_local_server(
                port=3000,
                authorization_prompt_message='Please visit this URL: {url}',
                success_message='The auth flow is complete; you may close this window.',
                open_browser=True
            )
            
            self._save_credentials()
            return self.credentials
        except Exception as e:
            print(f"Error in OAuth flow: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Authentication failed: {str(e)}. Please ensure your redirect URIs are properly configured in Google Cloud Console."
            )
    
    def _save_credentials(self):
        """Save credentials to the token file."""
        if self.credentials and self.credentials.valid:
            with open(self.token_file, 'w') as token:
                token.write(self.credentials.to_json())
            print("Credentials saved successfully")
            
    def revoke_token(self):
        """Revoke the current token."""
        if self.credentials and self.credentials.valid:
            try:
                request = Request()
                self.credentials.refresh(request)
                response = request.post(
                    'https://oauth2.googleapis.com/revoke',
                    params={'token': self.credentials.token},
                    headers={'content-type': 'application/x-www-form-urlencoded'}
                )
                
                if response.status_code == 200:
                    print("Token successfully revoked")
                    if os.path.exists(self.token_file):
                        os.remove(self.token_file)
                    return True
            except Exception as e:
                print(f"Error revoking token: {e}")
        return False