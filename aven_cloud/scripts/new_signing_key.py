"""Create the Ed25519 key pair used to sign entitlements.

    python scripts/new_signing_key.py

Put the private key in the server's AVEN_ENTITLEMENT_SIGNING_KEY secret, and the public
key in the desktop build (AVEN_ENTITLEMENT_PUBLIC_KEY, written into assets/cloud.json by
the build script). Never commit the private key.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

key = Ed25519PrivateKey.generate()
private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
print("AVEN_ENTITLEMENT_SIGNING_KEY (server secret):", base64.b64encode(private).decode())
print("AVEN_ENTITLEMENT_PUBLIC_KEY (desktop build): ", base64.b64encode(public).decode())
