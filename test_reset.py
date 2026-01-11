import os, smtplib
from email.mime.text import MIMEText

print("EMAIL:", os.getenv("EMAIL_ADDRESS"))
print("PASS:", bool(os.getenv("EMAIL_PASSWORD")))

msg = MIMEText("Test email from FREEDRIVE project")
msg["Subject"] = "SMTP Test"
msg["From"] = os.getenv("EMAIL_ADDRESS")
msg["To"] = os.getenv("EMAIL_ADDRESS")

server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
server.login(os.getenv("EMAIL_ADDRESS"), os.getenv("EMAIL_PASSWORD"))
server.send_message(msg)
server.quit()

print("Email sent successfully")
