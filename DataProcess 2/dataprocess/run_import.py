#!/usr/bin/env python3
"""Run mysql.ipynb cells 0-20 end-to-end."""
import json
import logging
import os
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

for k in list(os.environ):
    if k.startswith("MYSQL_"):
        del os.environ[k]

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

# ensure database exists (connect without default db if needed)
from sqlalchemy import create_engine, text

host = os.getenv("MYSQL_HOST")
port = os.getenv("MYSQL_PORT", "3306")
user = os.getenv("MYSQL_USER")
password = os.getenv("MYSQL_PASSWORD", "")
database = os.getenv("MYSQL_DATABASE")
server_url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/?charset=utf8mb4"
eng = create_engine(server_url, pool_pre_ping=True)
with eng.begin() as conn:
    conn.execute(text(
        f"CREATE DATABASE IF NOT EXISTS `{database}` "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    ))
eng.dispose()

nb = json.loads((ROOT / "mysql.ipynb").read_text(encoding="utf-8"))
ns = {"__name__": "__main__"}
for i in range(0, 21):
    cell = nb["cells"][i]
    if cell.get("cell_type") != "code":
        continue
    src = "".join(cell.get("source") or []).strip()
    if not src:
        continue
    title = src.splitlines()[0][:60]
    print(f"\n===== CELL {i}: {title} =====", flush=True)
    try:
        exec(compile(src, f"cell_{i}", "exec"), ns, ns)
        print(f"CELL {i} OK", flush=True)
    except Exception:
        print(f"CELL {i} FAILED", flush=True)
        traceback.print_exc()
        raise SystemExit(1)

print("\n===== ALL DONE =====")
