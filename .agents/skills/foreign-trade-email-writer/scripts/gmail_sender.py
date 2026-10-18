#!/usr/bin/env python3
"""
Foreign Trade Email Writer - Gmail Sender
使用 Gmail API 发送邮件
复用 foreign-trade-email-sorter 的认证配置
"""

import os
import sys
import base64
import argparse
from datetime import datetime
from email.mime.text import MIMEText

# 尝试导入Google API
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
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]


def get_gmail_service():
    """获取Gmail API服务"""
    # 首先尝试从 email-sorter 复用 token
    sorter_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                              'foreign-trade-email-sorter')
    
    # 本目录
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 尝试的路径
    token_paths = [
        os.path.join(sorter_dir, 'token.json'),  # 从 sorter 复用
        os.path.join(base_dir, 'token.json'),    # 本目录
    ]
    
    credentials_paths = [
        os.path.join(sorter_dir, 'credentials.json'),  # 从 sorter 复用
        os.path.join(base_dir, 'credentials.json'),    # 本目录
    ]
    
    creds = None
    token_path = None
    credentials_path = None
    
    # 查找 token
    for path in token_paths:
        if os.path.exists(path):
            token_path = path
            print(f"Found token: {path}")
            break
    
    # 查找 credentials
    for path in credentials_paths:
        if os.path.exists(path):
            credentials_path = path
            print(f"Found credentials: {path}")
            break
    
    if not credentials_path:
        print("Error: credentials.json not found")
        print("Please copy credentials.json from foreign-trade-email-sorter or create new one")
        return None
    
    # 加载或创建 token
    if token_path and os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            print("Loaded existing token")
        except Exception as e:
            print(f"Error loading token: {e}")
            creds = None
    
    # 如果 token 无效或没有发送权限，需要重新授权
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("Token refreshed")
            except Exception as e:
                print(f"Error refreshing token: {e}")
                creds = None
        
        if not creds:
            print("\nAuthorization required to send emails...")
            print("Opening browser for Gmail authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            print("Authorization successful!")
        
        # 保存 token 到本目录
        token_save_path = os.path.join(base_dir, 'token.json')
        with open(token_save_path, 'w') as token:
            token.write(creds.to_json())
        print(f"Token saved to: {token_save_path}")
    
    return build('gmail', 'v1', credentials=creds)


def create_message(sender, to, subject, body):
    """创建邮件消息"""
    message = MIMEText(body, 'plain', 'utf-8')
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}


def send_email(service, sender, to, subject, body):
    """发送邮件"""
    try:
        message = create_message(sender, to, subject, body)
        result = service.users().messages().send(userId='me', body=message).execute()
        print("[OK] Email sent successfully!")
        print(f"   To: {to}")
        print(f"   Subject: {subject}")
        print(f"   Message ID: {result['id']}")
        return True
    except Exception as e:
        print(f"[Error] Failed to send email: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Send email via Gmail API')
    parser.add_argument('--to', required=True, help='Recipient email address')
    parser.add_argument('--subject', required=True, help='Email subject')
    parser.add_argument('--body', required=True, help='Email body (file path or text)')
    parser.add_argument('--body-file', action='store_true', help='Treat body as file path')
    
    args = parser.parse_args()
    
    # 获取邮件内容
    if args.body_file:
        with open(args.body, 'r', encoding='utf-8') as f:
            body = f.read()
    else:
        body = args.body
    
    # 获取 Gmail 服务
    service = get_gmail_service()
    if not service:
        print("Failed to get Gmail service")
        sys.exit(1)
    
    # 获取发件人邮箱
    profile = service.users().getProfile(userId='me').execute()
    sender = profile['emailAddress']
    print(f"\nSending from: {sender}")
    
    # 发送邮件
    success = send_email(service, sender, args.to, args.subject, body)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
