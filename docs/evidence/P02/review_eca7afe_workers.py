"""Synthetic worker for the independent P02 deadline probe. No PoB values."""
import time
from synthetic_workers import SyntheticSession


class SlowLoadSession(SyntheticSession):
    def handle(self, op, args):
        if op == "load_exact_build":
            time.sleep(1.0)
        return super().handle(op, args)
