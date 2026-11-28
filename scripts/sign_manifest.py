"""Create an Ed25519 signing key pair and sign release manifests.

    python scripts/sign_manifest.py keygen PRIVATE_KEY_FILE
    python scripts/sign_manifest.py sign PRIVATE_KEY_FILE MANIFEST_FILE

`keygen` writes the private key to the file (owner-only on POSIX) and prints the public key to paste into
`UPDATE_PUBLIC_KEY` in profile_switch/updates.py. Keep the private key out of the repository.
`sign` prints the base64 signature of the manifest file's exact bytes; publish it next to the manifest.
"""

import argparse
import base64
import os
from pathlib import Path
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

RAW = serialization.Encoding.Raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("keygen").add_argument("private_key", type=Path)
    sign = commands.add_parser("sign")
    sign.add_argument("private_key", type=Path)
    sign.add_argument("manifest", type=Path)
    options = parser.parse_args(argv)
    if options.command == "keygen":
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(RAW, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        try:
            descriptor = os.open(options.private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            print(f"Refusing to overwrite {options.private_key}.", file=sys.stderr)
            return 1
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(base64.b64encode(private).decode("ascii") + "\n")
        public = key.public_key().public_bytes(RAW, serialization.PublicFormat.Raw)
        print(base64.b64encode(public).decode("ascii"))
        return 0
    private = base64.b64decode(options.private_key.read_text(encoding="ascii").strip(), validate=True)
    key = Ed25519PrivateKey.from_private_bytes(private)
    print(base64.b64encode(key.sign(options.manifest.read_bytes())).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
