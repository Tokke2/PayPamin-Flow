"""Backward-compatible entry point for the shared PayPamin Flow launcher."""
from paypamin_flow_launcher import run


if __name__ == "__main__":
    raise SystemExit(run())
