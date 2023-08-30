'''ファイルを添付したメールを送信する'''
import sys
import smtplib
from email.mime import multipart
from email.mime import text
from email.mime.application import MIMEApplication

smtp_host = 'smtp.gmail.com'
smtp_port = 587

# from_email = 'xxxx@example.com'
# username = 'xxxx@example.com'
# app_password = 'xxxxxxxxx'

msg = multipart.MIMEMultipart()
msg['Subject'] = 'log files from bt-01'
# msg['From'] = from_email
# msg['To'] = to_email
msg.attach(text.MIMEText('Test email', 'plain'))        # 本文

# ファイル名はシェルスクリプトからもらう引数にする
# 送出先も引数でもらう（一つだけ）

# check argument number
args = sys.argv
if 5 != len(args):
    print('Require five arguments, sendlog.py, file name, from_email address, from_email app-password, and to_email address')
    exit(1)

# set file name and to_email
attachedfilename = args[1]
from_email = args[2]
appPassword = args[3]
to_email = args[4]
msg['From'] = from_email
msg['To'] = to_email
username = from_email
app_password = appPassword

try:
    with open(attachedfilename, 'rb') as f:
        attachment = MIMEApplication(f.read())
        attachment.add_header(
            'Content-Disposition', 'attachment',
            filename=attachedfilename
        )
        msg.attach(attachment)
except Exception as e:
    print(f'[ERROR] {type(e)}:{str(e)}')
    exit(1)


# attach bt id file (bt_id.txt)
try:
    with open('bt_id.txt', 'r') as f:
        attachment = text.MIMEText(f.read())
        attachment.add_header(
            'Content-Disposition', 'attachment',
            filename='bt_id.txt'
        )
        msg.attach(attachment)
except Exception as e:
    print(f'[ERROR] {type(e)}:{str(e)}')
    exit(1)


server = smtplib.SMTP(smtp_host, smtp_port)
server.ehlo()
server.starttls()
server.ehlo()
server.login(username, app_password)
server.send_message(msg)
server.quit()
