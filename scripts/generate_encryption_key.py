"""Generate a 32-byte base64-encoded encryption master key."""

import base64
import os


def main():
    key = os.urandom(32)
    encoded = base64.b64encode(key).decode("utf-8")
    print(f"OAUPA_MASTER_KEY={encoded}")


if __name__ == "__main__":
    main()
