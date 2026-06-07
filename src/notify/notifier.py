import logging

from src.notify.email import send_email
from src.decision.models import Decision

logger = logging.getLogger(__name__)


def _resolve_weights(decision: Decision) -> dict[str, float]:
    return (
        decision.final_weights
        or decision.sized_weights #remove these once vol and conviction modelling complete
        or decision.base_weights
        or {}
    )


def send_notification(
    decision: Decision,
    price_signals,
    macro_signals,
):
    weights = _resolve_weights(decision)

    logger.debug("=== Daily Allocation Decision ===")
    logger.debug("Date: %s", decision.date)

    logger.debug("ALLOCATIONS:")
    for asset, w in weights.items():
        logger.debug("  %s: %.2f%%", asset, w * 100)

    logger.debug("Reason: %s", decision.reason)

    alloc_lines = "\n".join(
        f"{asset}: {w:.2%}" for asset, w in weights.items()
    )

    body = f"""
Daily Allocation Decision

Date:
{decision.date}

Regime:
{decision.regime}

Allocations:
{alloc_lines}

Reason:
{decision.reason}
"""

    send_email(
        subject=f"Daily Strategy Allocation — {decision.date}",
        body=body.strip(),
    )