from dotenv import load_dotenv
load_dotenv()

from src.notify.email import send_email

send_email(
    subject="SMTP Test",
    body="If you see this, email is wired correctly."
)
