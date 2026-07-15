# -*- coding: utf-8 -*-
"""
Dong bo CHI PHAN CUSTOMER_CODE_PREFIX_TO_REGION (bang 63 tien to ma khach hang -> vung mien) tu
src/region_map.py (D:\\DNH, nguon xay dung + kiem chung) sang backend/region_map.py (DNH-x-MCNA,
repo Python rieng cua chatbot moi) - KHONG copy de nguyen file, vi 2 repo co cau truc file khac nhau
(D:\\DNH con co REGION_SQL_MARKERS/REGION_NAMES_VI rieng cho tuong thich voi ai_agent/chatbot.py cu,
DNH-x-MCNA khong can phan do).

Dung boi .github/workflows/sync-region-map-to-mcna.yml (GitHub Action) - khong chay tay thuong xuyen.
Neu chay tay: py scripts/sync_customer_prefix_table.py <duong_dan_file_dich>
"""
import re
import sys
import pathlib

SRC_PATH = pathlib.Path(__file__).resolve().parent.parent / "src" / "region_map.py"

_DICT_RE = re.compile(
    r"CUSTOMER_CODE_PREFIX_TO_REGION\s*=\s*\{.*?\n\}",
    re.DOTALL,
)


def extract_prefix_table(src_text: str) -> str:
    m = _DICT_RE.search(src_text)
    if not m:
        raise ValueError("Khong tim thay CUSTOMER_CODE_PREFIX_TO_REGION trong src/region_map.py")
    return m.group(0)


def patch_dest(dest_text: str, new_block: str) -> str:
    if not _DICT_RE.search(dest_text):
        raise ValueError("File dich khong co CUSTOMER_CODE_PREFIX_TO_REGION de thay - kiem tra lai cau truc.")
    return _DICT_RE.sub(new_block, dest_text, count=1)


def main():
    if len(sys.argv) != 2:
        print("Dung: py scripts/sync_customer_prefix_table.py <duong_dan_backend/region_map.py_ben_MCNA>")
        sys.exit(1)
    dest_path = pathlib.Path(sys.argv[1])

    src_text = SRC_PATH.read_text(encoding="utf-8")
    new_block = extract_prefix_table(src_text)

    dest_text = dest_path.read_text(encoding="utf-8")
    patched = patch_dest(dest_text, new_block)

    if patched == dest_text:
        print("Khong co thay doi - bang tien to giong het ban dich, bo qua.")
        sys.exit(0)

    dest_path.write_text(patched, encoding="utf-8")
    print(f"Da cap nhat {dest_path} theo src/region_map.py.")


if __name__ == "__main__":
    main()
