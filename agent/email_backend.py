"""System email (forgot password) sent through the admin's Gmail from System settings."""
from django.core.mail.backends.smtp import EmailBackend


class SystemGmailBackend(EmailBackend):
    def __init__(self, **kwargs):
        from .models import SystemSettings

        s = SystemSettings.load()
        self.system_address = s.gmail_address
        super().__init__(host="smtp.gmail.com", port=587, username=s.gmail_address,
                         password=s.gmail_app_password, use_tls=True, timeout=20, **kwargs)

    def send_messages(self, email_messages):
        if not self.system_address:
            raise RuntimeError("System Gmail is not set up (Admin > System settings).")
        for m in email_messages:
            m.from_email = self.system_address
        return super().send_messages(email_messages)
