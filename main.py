import logging

from src.engine.run import run_engine
from src.context.live import LiveContext
from src.strategy.presets import live_strategy


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    context = LiveContext()
    # Live trades the single selected registry entry (LIVE_STRATEGY in
    # src/strategy/presets.py). Old implicit-default call kept as a safety net:
    # run_engine(context)
    run_engine(context, strategy=live_strategy())


if __name__ == "__main__":
    main()
