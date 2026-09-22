import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_otp_email(
    recipient_email: str,
    otp_code: str,
    purpose: str = "registration",
):
    if purpose == "registration":
        subject = "Research Assistant - Email Verification"
        message_text = (
            f"Your verification OTP is: {otp_code}\n\n"
            "This OTP is valid for a limited time.\n"
            "Do not share this OTP with anyone."
        )
    else:
        subject = "Research Assistant - Password Reset OTP"
        message_text = (
            f"Your password reset OTP is: {otp_code}\n\n"
            "Do not share this OTP with anyone."
        )

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient_email

    message.set_content(message_text)

    with smtplib.SMTP(
        settings.SMTP_HOST,
        settings.SMTP_PORT,
    ) as server:
        server.starttls()

        server.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD,
        )

        server.send_message(message)