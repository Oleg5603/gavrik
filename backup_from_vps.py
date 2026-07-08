"""Почасовой бэкап /root/gavrik с VPS на ПК (на случай падения сервера)."""
import sys
import time
from pathlib import Path

import paramiko
from dotenv import dotenv_values

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR.parent / "gavrik_vps_backup"
REMOTE_DIR = "/root/gavrik"
SKIP_DIRS = {"__pycache__", ".git"}


def download_dir(sftp, remote_path, local_path):
    local_path.mkdir(parents=True, exist_ok=True)
    for entry in sftp.listdir_attr(remote_path):
        name = entry.filename
        r = f"{remote_path}/{name}"
        l = local_path / name
        import stat
        if stat.S_ISDIR(entry.st_mode):
            if name in SKIP_DIRS:
                continue
            download_dir(sftp, r, l)
        else:
            sftp.get(r, str(l))


def main():
    v = dotenv_values(BASE_DIR / ".env")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(v["VPS_HOST"], username=v["VPS_USER"], password=v["VPS_PASSWORD"], timeout=15)
    sftp = client.open_sftp()
    download_dir(sftp, REMOTE_DIR, BACKUP_DIR)
    sftp.close()
    client.close()
    stamp_file = BACKUP_DIR / "last_backup.txt"
    stamp_file.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    print(f"OK: backup updated at {BACKUP_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"BACKUP FAILED: {e}", file=sys.stderr)
        sys.exit(1)
