"""Rotate local privileged passwords without calling any external API.

Run on the backend host after pulling the security release and before reopening the service.
The generated passwords are printed once to the local console; store them securely.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import auth  # noqa: E402


DEFAULT_PRIVILEGED_USERS = ("dnh", "admin.dnh")


def rotate_user(username: str) -> str | None:
    user = auth.get_user_by_email_or_username(username)
    if not user:
        return None
    password = auth.generate_password(20)
    if not auth.set_password(username, password, must_change_password=True):
        raise RuntimeError(f"Khong the doi mat khau cho {username}")
    auth.delete_all_sessions_for_user(user["id"])
    return password


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xoay mat khau tai khoan dac quyen va thu hoi toan bo session."
    )
    parser.add_argument(
        "usernames", nargs="*", default=list(DEFAULT_PRIVILEGED_USERS),
        help="Username can xoay (mac dinh: dnh admin.dnh)",
    )
    args = parser.parse_args()

    auth.init_schema()
    rotated = 0
    for username in args.usernames:
        password = rotate_user(username.strip().lower())
        if password is None:
            print(f"BO QUA {username}: khong ton tai")
            continue
        rotated += 1
        print(f"DA XOAY {username}: {password}")
    print(f"Hoan tat: {rotated}/{len(args.usernames)} tai khoan da duoc xoay; session cu da bi thu hoi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
