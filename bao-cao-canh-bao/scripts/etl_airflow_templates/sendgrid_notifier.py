"""
DNH Mail Notification Service (SendGrid / AWS SES Helper)
Sends daily 7:00 AM reports and smart alerts to C-Level / Managers.
"""

import os
import boto3
from botocore.exceptions import ClientError
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

def send_via_sendgrid(to_emails, subject, html_content):
    """
    Gui email thong bao su dung SendGrid API.
    Yeu cau bien moi truong SENDGRID_API_KEY.
    """
    api_key = os.environ.get('SENDGRID_API_KEY')
    if not api_key:
        print("[ERROR] Thieu bien moi truong SENDGRID_API_KEY. Khong the gui email.")
        return False
        
    sg = SendGridAPIClient(api_key=api_key)
    from_email = Email("reports@namhapharma.com", "DWH Duoc Nam Ha")
    destinations = [To(email) for email in to_emails]
    
    mail = Mail(
        from_email=from_email,
        to_emails=destinations,
        subject=subject,
        plain_text_content=None,
        html_content=Content("text/html", html_content)
    )
    
    try:
        response = sg.client.mail.send.post(request_body=mail.get())
        print(f"[SendGrid SUCCESS] Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"[SendGrid ERROR] Gap loi khi goi API SendGrid: {str(e)}")
        return False

def send_via_aws_ses(to_emails, subject, html_content, region_name="us-east-1"):
    """
    Gui email thong bao su dung Amazon AWS SES.
    Yeu cau credentials AWS duoc config trong ~\.aws\credentials hoac qua IAM Role.
    """
    sender = "DWH Duoc Nam Ha <reports@namhapharma.com>"
    charset = "UTF-8"
    
    # Khoi tao AWS SES Client
    client = boto3.client('ses', region_name=region_name)
    
    try:
        response = client.send_email(
            Destination={
                'ToAddresses': to_emails,
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': charset,
                        'Data': html_content,
                    },
                },
                'Subject': {
                    'Charset': charset,
                    'Data': subject,
                },
            },
            Source=sender,
        )
        print(f"[AWS SES SUCCESS] Email da duoc gui! MessageID: {response['MessageId']}")
        return True
    except ClientError as e:
        print(f"[AWS SES ERROR] Gap loi khi gui email qua AWS SES: {e.response['Error']['Message']}")
        return False

if __name__ == "__main__":
    # Test execution
    test_recipients = ["test-manager@namhapharma.com"]
    test_subject = "[DNH Test] Kiem tra ket noi Email Service"
    test_html = """
    <html>
        <body>
            <h2>He thong thong bao DWH Duoc Nam Ha</h2>
            <p>Day la email kiem tra he thong alert thong minh.</p>
        </body>
    </html>
    """
    
    print("Moi truong cua ban da san sang. Vui long import file nay de su dung.")
