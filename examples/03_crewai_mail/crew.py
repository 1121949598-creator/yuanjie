from crewai import Agent
from crewai.tools import tool


@tool
def send_approved_email(recipient: str, body: str) -> str:
    """Send an email after explicit human confirmation and allowlist validation."""
    require_human_confirmation(recipient, body)
    if recipient not in ALLOWED_RECIPIENTS:
        raise ValueError("recipient not in allowlist")
    return mail_client.send(recipient, body)


mailer = Agent(role="Customer notification operator", goal="Send approved customer notifications by email", backstory="Every send requires human approval", tools=[send_approved_email])
