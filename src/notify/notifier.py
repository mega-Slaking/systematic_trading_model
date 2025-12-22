from src.notify.email import send_email


def send_notification(decision: dict,
                      price_signals,
                      macro_signals):
    #for now, just print to console email/text integrations later
    print("=== Daily Decision ===")
    print(f"Date:   {decision['date']}")
    print(f"HOLD:   {decision['chosen']}")
    print(f"Reason: {decision['reason']}")
    body = f"""
Daily Allocation Decision

Date:   {decision['date']}
Hold:   {decision['chosen']}
Reason: {decision['reason']}
"""

    send_email(
        subject=f"Daily Strategy Decision — {decision['chosen']}",
        body=body.strip()
    )