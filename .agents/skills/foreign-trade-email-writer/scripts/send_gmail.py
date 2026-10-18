#!/usr/bin/env python3
"""
Foreign Trade Email Writer - Gmail Sender
使用 Gmail API 发送邮件
"""

import os
import sys
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Google API
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    print("Error: Google API libraries not installed.")
    print("Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    sys.exit(1)

# 权限范围 - 需要发送邮件权限
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    """获取 Gmail API 服务（发送权限）"""
    creds = None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_dir, 'token_send.json')  # 使用独立的token
    credentials_path = os.path.join(base_dir, 'credentials.json')
    
    # 检查 credentials.json
    if not os.path.exists(credentials_path):
        # 尝试从 email-sorter 复制
        sorter_credentials = os.path.join(base_dir, '..', '..', 'foreign-trade-email-sorter', 'credentials.json')
        if os.path.exists(sorter_credentials):
            import shutil
            shutil.copy(sorter_credentials, credentials_path)
            print(f"Copied credentials from email-sorter")
        else:
            print(f"Error: credentials.json not found")
            print(f"Please place credentials.json in: {base_dir}")
            return None
    
    # 加载 token
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # 授权流程
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            print("Opening browser for Gmail authorization (Send permission)...")
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        print("Authorization successful!")
    
    return build('gmail', 'v1', credentials=creds)


def create_message(sender, to, subject, body):
    """创建邮件消息"""
    message = MIMEMultipart()
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    
    msg = MIMEText(body, 'plain', 'utf-8')
    message.attach(msg)
    
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}


def send_message(service, user_id, message):
    """发送邮件"""
    try:
        result = service.users().messages().send(userId=user_id, body=message).execute()
        print(f"Message Id: {result['id']}")
        return result
    except Exception as e:
        print(f"Error sending message: {e}")
        return None


def main():
    """主函数"""
    if len(sys.argv) < 5:
        print("Usage: python send_gmail.py <to_email> <subject> <body_file> <sender_email>")
        print("Example: python send_gmail.py 'client@example.com' 'Hello' 'email_body.txt' 'your@gmail.com'")
        sys.exit(1)
    
    to_email = sys.argv[1]
    subject = sys.argv[2]
    body_file = sys.argv[3]
    sender_email = sys.argv[4]
    
    # 读取邮件正文
    if not os.path.exists(body_file):
        print(f"Error: Body file not found: {body_file}")
        sys.exit(1)
    
    with open(body_file, 'r', encoding='utf-8') as f:
        body = f.read()
    
    print(f"Sending email to: {to_email}")
    print(f"Subject: {subject}")
    
    # 获取服务
    service = get_gmail_service()
    if not service:
        sys.exit(1)
    
    # 创建并发送邮件
    message = create_message(sender_email, to_email, subject, body)
    result = send_message(service, 'me', message)
    
    if result:
        print("Email sent successfully!")
    else:
        print("Failed to send email")
        sys.exit(1)


if __name__ == '__main__':
    main()
