from src.notify.email import send_email


def send_notification(
        decision: dict,
        price_signals,
        macro_signals):

    weights = decision.get("weights", {})

    print("=== Daily Allocation Decision ===")
    print(f"Date: {decision['date']}")

    print("ALLOCATIONS:")
    for asset, w in weights.items():
        print(f"  {asset}: {w:.2%}")

    print(f"Reason: {decision['reason']}")

    # build allocation text
    alloc_lines = "\n".join(
        f"{asset}: {w:.2%}" for asset, w in weights.items()
    )

    body = f"""
Daily Allocation Decision

Date:
{decision['date']}

Allocations:
{alloc_lines}

Reason:
{decision['reason']}
"""

    send_email(
        subject=f"Daily Strategy Allocation — {decision['date']}",
        body=body.strip()
    )