import os
import smtplib
import ssl
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

def send_otp_email(
    recipient_email: str,
    otp_code: str,
    purpose: str = "registration",
):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(
        os.getenv("SMTP_PORT", "587")
    )
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")

    if not smtp_host:
        raise RuntimeError(
            "SMTP_HOST is not configured"
        )

    if not smtp_username:
        raise RuntimeError(
            "SMTP_USERNAME is not configured"
        )

    if not smtp_password:
        raise RuntimeError(
            "SMTP_PASSWORD is not configured"
        )

    if not smtp_from:
        raise RuntimeError(
            "SMTP_FROM is not configured"
        )

    if purpose == "registration":
        subject = (
            "Research Assistant - Email Verification"
        )

        message_text = (
            f"Your verification OTP is: {otp_code}\n\n"
            "This OTP is valid for a limited time.\n"
            "Do not share this OTP with anyone."
        )

    elif purpose == "password_setup":
        subject = (
            "Research Assistant - Password Setup Verification"
        )

        message_text = (
            f"Your password setup verification code is: {otp_code}\n\n"
            "This code is valid for a limited time.\n"
            "Do not share this code with anyone."
        )

    else:
        subject = (
            "Research Assistant - Password Reset OTP"
        )

        message_text = (
            f"Your password reset OTP is: {otp_code}\n\n"
            "Do not share this OTP with anyone."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = recipient_email
    message.set_content(message_text)

    context = ssl.create_default_context()

    try:

        if smtp_port == 587:
            with smtplib.SMTP(
                smtp_host,
                smtp_port,
                timeout=20,
            ) as server:

                server.ehlo()
                server.starttls(
                    context=context
                )
                server.ehlo()

                server.login(
                    smtp_username,
                    smtp_password,
                )

                server.send_message(message)

        elif smtp_port == 465:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                context=context,
                timeout=20,
            ) as server:

                server.login(
                    smtp_username,
                    smtp_password,
                )

                server.send_message(message)

        else:
            raise RuntimeError(
                "Unsupported SMTP port. Use 587 or 465."
            )

        print(
            f"OTP email sent successfully to {recipient_email}"
        )

        return True

    except smtplib.SMTPAuthenticationError as error:
        print(
            f"SMTP authentication failed: {error}"
        )

        raise RuntimeError(
            "Email login failed. Check SMTP username and app password."
        )

    except smtplib.SMTPException as error:
        print(
            f"SMTP error: {error}"
        )

        raise RuntimeError(
            f"SMTP email sending failed: {error}"
        )

    except Exception as error:
        print(
            f"Email sending error: {error}"
        )

        raise RuntimeError(
            f"Unable to send OTP email: {error}"
        )
