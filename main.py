from src.engine.run import run_engine
from src.context.live import LiveContext

def main():
    context = LiveContext()
    run_engine(context)

if __name__ == "__main__":
    main()
