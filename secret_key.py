import os

# Generate a secure random key (24 bytes)
secret_key = os.urandom(24).hex()
print(secret_key)