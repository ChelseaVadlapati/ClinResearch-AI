"""Create local demo configuration with a fresh random password; never overwrite."""

import secrets
from pathlib import Path

password = secrets.token_hex(24)
path = Path(".env")
with path.open("x") as output:
    path.chmod(0o600)
    output.write(
        f"POSTGRES_USER=clinresearch\nPOSTGRES_DB=clinresearch\n"
        f"POSTGRES_PASSWORD={password}\n"
        f"DATABASE_URL=postgresql+psycopg://clinresearch:{password}@localhost:5432/clinresearch\n"
        "API_BASE_URL=http://localhost:8000\n"
    )
print("Created .env with a generated local password. Do not commit this file.")
