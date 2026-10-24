import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("GITHUB_APP_ID", "12345")
os.environ.setdefault(
    "GITHUB_APP_PRIVATE_KEY",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----",
)
