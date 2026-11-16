"""Compatibility launcher; business services live in sau_core."""
from sau_web.launcher import main


if __name__ == "__main__":
    raise SystemExit(main())
