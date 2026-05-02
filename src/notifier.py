"""SMS notifications via Twilio."""
import logging
import os

log = logging.getLogger(__name__)


def send_sms(body: str) -> None:
    """Send an SMS. Silently no-ops (with a warning) if creds aren't set."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_num = os.environ.get("TWILIO_FROM")
    to_num = os.environ.get("NOTIFY_TO")

    if not all([sid, token, from_num, to_num]):
        log.warning(
            "Twilio creds incomplete (need TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "TWILIO_FROM, NOTIFY_TO). Would have sent: %s",
            body,
        )
        return

    # Imported lazily so dry runs don't require the twilio package.
    from twilio.rest import Client

    client = Client(sid, token)
    msg = client.messages.create(body=body, from_=from_num, to=to_num)
    log.info("SMS sent (sid=%s)", msg.sid)
