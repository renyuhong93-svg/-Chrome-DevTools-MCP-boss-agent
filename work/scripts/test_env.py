from __future__ import annotations

from pprint import pprint

from src.core import load_settings, verify_runtime_environment


if __name__ == "__main__":
    pprint(verify_runtime_environment(load_settings()))
