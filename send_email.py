import os
import base64
import mimetypes
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
import json
from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr
import uvicorn

# Import our custom OAuth manager
from oauth_manager import OAuthManager

# Initialize FastAPI app
app = FastAPI(
    title="Email Sending API",
    description="API for sending emails with attachments using Gmail API",
    version="1.0.0"
)

# Initialize OAuth manager
oauth_manager = OAuthManager()

def get_oauth_credentials():
    """Dependency for getting OAuth credentials"""
    return oauth_manager.get_credentials()


def create_message_with_attachments(sender, to, subject, message_text, file_paths):
    """Create a message for an email with attachments.

    Args:
        sender: Email address of the sender.
        to: Email address of the receiver.
        subject: The subject of the email message.
        message_text: The text of the email message.
        file_paths: List of paths to files to be attached.

    Returns:
        An object containing a base64url encoded email object.
    """
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    message['date'] = formatdate(localtime=True)

    # Add message body
    msg = MIMEText(message_text)
    message.attach(msg)

    # Add attachments
    for file_path in file_paths:
        content_type, encoding = mimetypes.guess_type(file_path)

        if content_type is None or encoding is not None:
            content_type = 'application/octet-stream'

        main_type, sub_type = content_type.split('/', 1)
        
        if main_type == 'text':
            with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                msg = MIMEText(file.read())
        elif main_type == 'image':
            with open(file_path, 'rb') as file:
                msg = MIMEImage(file.read(), _subtype=sub_type)
        elif main_type == 'audio':
            with open(file_path, 'rb') as file:
                msg = MIMEAudio(file.read(), _subtype=sub_type)
        else:
            # Handle all other file types as binary (including PDF, Word, Excel)
            with open(file_path, 'rb') as file:
                msg = MIMEBase(main_type, sub_type)
                msg.set_payload(file.read())
                # Encode the payload using Base64
                import email.encoders
                email.encoders.encode_base64(msg)
            
        filename = os.path.basename(file_path)
        msg.add_header('Content-Disposition', 'attachment', filename=filename)
        message.attach(msg)

    # Encode message for sending
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}


def send_message(service, user_id, message):
    """Send an email message.

    Args:
        service: Authorized Gmail API service instance.
        user_id: User's email address. The special value "me" can be used to
                 indicate the authenticated user.
        message: Message to be sent.

    Returns:
        Sent Message ID.
    """
    try:
        sent_message = service.users().messages().send(
            userId=user_id, body=message).execute()
        print(f'Message Id: {sent_message["id"]}')
        return sent_message
    except HttpError as error:
        print(f'An error occurred: {error}')


# Define API data models
class Recipient(BaseModel):
    email: str
    subject: str
    body: str
    attachments: Optional[List[str]] = []

class EmailRequest(BaseModel):
    recipients: List[Recipient]

class EmailResponse(BaseModel):
    success: bool
    message: str
    failed_recipients: List[str] = []
    success_count: int = 0

async def send_email_task(recipient: Recipient):
    """Background task to send email to a recipient"""
    try:
        # Get fresh credentials with automatic token refresh
        creds = oauth_manager.get_credentials()
        service = build('gmail', 'v1', credentials=creds)
        
        # Prepare attachment file paths
        file_paths = []
        for attachment_name in recipient.attachments:
            file_path = os.path.join('attachments', attachment_name)
            if os.path.isfile(file_path):
                file_paths.append(file_path)
        
        # Create and send email
        message = create_message_with_attachments(
            'me', recipient.email, recipient.subject, recipient.body, file_paths)
        
        send_message(service, 'me', message)
        return True
    except Exception as e:
        print(f"Error sending email to {recipient.email}: {e}")
        return False

@app.post("/send-emails", response_model=EmailResponse)
async def send_emails(background_tasks: BackgroundTasks, request: EmailRequest):
    """Send emails to multiple recipients with custom subjects, bodies, and attachments"""
    response = EmailResponse(success=True, message="Processing email requests")
    
    for recipient in request.recipients:
        background_tasks.add_task(send_email_task, recipient)
    
    return EmailResponse(
        success=True,
        message=f"Processing {len(request.recipients)} email requests in the background"
    )

@app.get("/")
async def root():
    """Root endpoint that provides API information"""
    return {"message": "Welcome to the Email Sending API. Use /send-emails to send emails."}

@app.get("/auth/status")
async def auth_status():
    """Check the status of OAuth credentials"""
    try:
        creds = oauth_manager.get_credentials()
        if not creds:
            return {
                "authenticated": False,
                "message": "No valid credentials found"
            }
        
        expiry = creds.expiry.isoformat() if creds.expiry else "Unknown"
        return {
            "authenticated": True,
            "token_expiry": expiry,
            "scopes": creds.scopes
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e)
        }

@app.post("/auth/revoke")
async def revoke_auth():
    """Revoke the current OAuth token"""
    success = oauth_manager.revoke_token()
    if success:
        return {"success": True, "message": "Token successfully revoked"}
    else:
        return {"success": False, "message": "Failed to revoke token or no valid token found"}

@app.post("/auth/refresh")
async def force_refresh():
    """Force a token refresh"""
    try:
        # Set token as expired to force refresh
        if oauth_manager.credentials:
            import datetime
            oauth_manager.credentials.expiry = datetime.datetime.utcnow()
        
        # Get fresh credentials
        creds = oauth_manager.get_credentials()
        return {
            "success": True,
            "message": "Token refreshed successfully",
            "expiry": creds.expiry.isoformat() if creds.expiry else "Unknown"
        }
    except Exception as e:
        return {
            "success": False, 
            "message": f"Failed to refresh token: {str(e)}"
        }

if __name__ == '__main__':
    uvicorn.run("send_email:app", host="0.0.0.0", port=3000, reload=True)
