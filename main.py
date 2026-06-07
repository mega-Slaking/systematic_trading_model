import logging

from src.engine.run import run_engine
from src.context.live import LiveContext


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    context = LiveContext()
    run_engine(context)


if __name__ == "__main__":
    main()
