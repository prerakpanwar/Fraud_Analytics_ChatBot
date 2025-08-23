# notifier.py (UPDATED with feedback links)
from abc import ABC, abstractmethod
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """Abstract base class for all types of alerts."""

    @abstractmethod
    def send(self, transaction: dict, probability: float):
        pass


class EmailNotifier(Notifier):
    def __init__(
        self,
        sender,
        password,
        receiver,
        feedback_base_url="http://localhost:5000/feedback",
    ):
        self.sender = sender
        self.password = password
        self.receiver = receiver
        self.feedback_base_url = feedback_base_url

    def send(self, transaction: dict, probability: float):
        subject = f"🚨 Fraud Alert: Transaction Number -- {transaction['trans_num']}"

        # Mask credit card number (show only last 4 digits)
        cc_masked = "**** **** **** " + str(transaction.get("cc_num", ""))[-4:]

        # Extract relevant info
        date_time = transaction.get("trans_date_trans_time", "N/A")
        merchant = transaction.get("merchant", "N/A")
        if merchant.startswith("fraud_"):
            merchant = merchant.replace("fraud_", "")
        category = transaction.get("category", "N/A")
        lat = transaction.get("merch_lat", "N/A")
        lon = transaction.get("merch_long", "N/A")
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"

        # Feedback links
        trans_id = transaction["trans_num"]
        fraud_yes = f"{self.feedback_base_url}?trans_num={trans_id}&correct=1"
        fraud_no = f"{self.feedback_base_url}?trans_num={trans_id}&correct=0"

        body = f"""
🚨 Unusual Transaction Detected!

💳 Card Number: {cc_masked}
🕒 Date & Time: {date_time}
📟 Transaction #: {transaction['trans_num']}
💰 Amount: ${transaction['amt']}
🏬 Merchant: {merchant}
🛍️ Category: {category}
📍 Location: {maps_url}

🛠️ Was this really fraud?
Yes: {fraud_yes}
No: {fraud_no}
        """

        msg = MIMEMultipart()
        msg["From"] = self.sender
        msg["To"] = self.receiver
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)
            logger.warning("📨 Fraud alert email sent!")
        except Exception as e:
            logger.error(f"❌ Failed to send email alert: {e}")
