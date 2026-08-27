# -*- coding: utf-8 -*-
"""26/08/2026: mang commit 470e3bd (29/07/2026, chi co tren nhanh `main`) sang `master`, va mo
rong sang 2 cho tuong tu trong src/etl.py ma 470e3bd CHUA cham toi.

BOI CANH THAT. DNH khong ghi snapshot KPI thang thanh MOT lan ma tach nhieu ngay theo vung. Xac
nhan Bravo 29/07/2026:
    SaveDate 2026-07-27 -> MB (102 NV) + MN (48 NV), KHONG co MT
    SaveDate 2026-07-28 -> CHI co MT (34 NV)
Ghim vao MAX(SaveDate) (cach lam cu) thi ngay giua thang chi thay MOT vung, bao "toan doi 48,7%"
trong khi thuc chat la rieng Mien Trung - hut 43,97 ty chi tieu 2 vung con lai. KHONG CO CANH BAO
NAO vi phep kiem lech chi tieu chi duyet cac vung CO MAT trong ket qua.

Doi chieu Bravo that 27/08/2026 (script kiem_snapshot.py): snapshot hom nay du 3 mien, 187 NV -
loi dang o dang TIEM AN (chi lo giua thang, cac thang da dong luon co 1 snapshot tron ven), khong
dang no ngay luc vien nay - nhung van la mot qua min cho neu khong va.

CACH KIEM: khong ket noi Bravo that (khong co BRAVO_SQL_* tren may dev). Chi kiem CHUOI SQL sinh
ra co dung mau "GROUP BY EmployeeCode roi JOIN lai lay dung SaveDate cua tung nguoi" hay khong -
day la diem phan biet DUY NHAT giua ban dung va ban sai, khong can du lieu that de kiem duoc.
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.alerts as alerts
import src.etl as etl


def _sql_cua_ham(module, ten_ham):
    """Lay nguyen van source code cua 1 ham - du de kiem CAU TRUC SQL ben trong ma khong can
    goi ham that (goi that se can ket noi Bravo, khong co tren may dev)."""
    return io.open(module.__file__, encoding="utf-8").read()


_ALERTS_SRC = _sql_cua_ham(alerts, None)
_ETL_SRC = _sql_cua_ham(etl, None)


# ---------------------------------------------------------------------------------------
# Hang so gop thang - phai co dung 1 noi (nguon su that duy nhat), etl.py tai dung qua import
# ---------------------------------------------------------------------------------------

def test_hang_so_gop_thang_dinh_nghia_dung_1_lan_o_alerts():
    assert hasattr(alerts, "_MONTH_START_OF_LATEST_SNAPSHOT_SQL")
    assert "DATEFROMPARTS" in alerts._MONTH_START_OF_LATEST_SNAPSHOT_SQL
    assert "MAX([SaveDate])" in alerts._MONTH_START_OF_LATEST_SNAPSHOT_SQL


def test_etl_khong_dinh_nghia_lai_hang_so_rieng():
    """etl.py phai TAI DUNG hang so cua alerts.py qua import, khong duoc chep lai chuoi
    DATEFROMPARTS rieng - chep lai la tao nguon su that thu hai, sua mot ben quen ben kia (dung
    loai loi da dinh voi is_ac ngay 26/08/2026)."""
    assert "DATEFROMPARTS" not in _ETL_SRC, (
        "etl.py dang tu dinh nghia cong thuc gop thang rieng thay vi import tu alerts.py")
    assert "_MONTH_START_OF_LATEST_SNAPSHOT_SQL as _month_start_sql" in _ETL_SRC


# ---------------------------------------------------------------------------------------
# Khong con noi nao ghim MOT SaveDate cho FACT_TongHopKhachHang trong 4 ham da sua
# ---------------------------------------------------------------------------------------

_MAU_GHIM_1_NGAY = "[SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang])"


def test_alerts_khong_con_ghim_mot_ngay():
    """Ca 3 diem trong alerts.py (get_bravo_manager_codes, get_bravo_kpi_tdv_snapshot,
    check_daily_kpi_pace_alert, check_kpi_milestone_drop_alert - 4 diem, phat hien qua chinh
    test nay khi no bat duoc diem thu 3 va thu 4 ma ban va dau tien bo sot) deu phai doi sang
    >= (khoang thang) thay vi = (dung 1 ngay)."""
    assert _MAU_GHIM_1_NGAY not in _ALERTS_SRC


def test_check_daily_kpi_pace_alert_co_cte_latest():
    """Diem thu 3 - ham rieng biet voi get_bravo_kpi_tdv_snapshot/get_daily_kpi_pace_snapshot,
    de sot khi chi doc theo ten ham quen thuoc trong commit goc 470e3bd."""
    doan = _ALERTS_SRC[_ALERTS_SRC.find("def check_daily_kpi_pace_alert"):]
    doan = doan[:doan.find("\ndef ", 10)]
    assert "GROUP BY [EmployeeCode]" in doan
    assert "JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]" in doan


def test_check_kpi_milestone_drop_alert_co_cte_latest():
    """Diem thu 4 - so sanh TDV qua NHIEU KY lich su nhung van chi lay chi tieu tu MOT snapshot
    moi nhat; vung bien mat khoi snapshot do thi TDV vung do bien mat khoi TOAN BO phep so sanh
    milestone, khong chi 1 ky."""
    doan = _ALERTS_SRC[_ALERTS_SRC.find("def check_kpi_milestone_drop_alert"):]
    doan = doan[:doan.find("\ndef ", 10)]
    assert "GROUP BY [EmployeeCode]" in doan
    assert "JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]" in doan


def test_etl_pace_snapshot_khong_con_ghim_mot_ngay():
    """get_daily_kpi_pace_snapshot - CHUA TUNG duoc 470e3bd cham toi, la lo hong rieng phat hien
    khi ra soat commit sang master 26/08/2026."""
    assert _MAU_GHIM_1_NGAY not in _ETL_SRC


def test_etl_reconciliation_khong_con_ghim_mot_ngay():
    """get_kpi_revenue_reconciliation - cung la lo hong CHUA TUNG duoc va, doi chieu doanh thu
    hoa don voi KPI se sai (thieu) khi vung bi mat khoi snapshot ngay hien tai."""
    # Khong the dung lai _MAU_GHIM_1_NGAY vi ham nay dung bang con FACT_TongHopKhachHang khac ten
    # bien (khong co alias) - kiem truc tiep cum "SaveDate] = (SELECT MAX" da bi xoa het.
    assert "= (SELECT MAX([SaveDate])" not in _ETL_SRC


# ---------------------------------------------------------------------------------------
# Ca 4 diem sua deu phai co dung mau CTE latest + JOIN lai theo tung ma - khong chi doi ky hieu
# so sanh (>=) ma con phai GOM DUNG theo tung nhan vien/khach hang, neu khong ket qua se PHONG TO
# (cong ca cac ngay khac trong thang cho cung 1 nguoi) thay vi dung.
# ---------------------------------------------------------------------------------------

def test_alerts_manager_codes_dung_khoang_thang():
    ham = alerts.get_bravo_manager_codes.__doc__ or ""
    assert "THÁNG" in ham or "_MONTH_START_OF_LATEST_SNAPSHOT_SQL" in ham


def test_alerts_kpi_tdv_snapshot_co_cte_latest_join_dung_ngay_tung_nguoi():
    """Bat loi PHONG TO: neu chi doi = thanh >= ma KHONG gom theo tung EmployeeCode roi JOIN lai
    dung SaveDate cua rieng ho, ket qua se CONG DON nhieu ngay cho cung 1 nguoi - tuong duong
    nhan doi/nhan ba doanh so. Day la diem tinh vi nhat cua ban va, khong the bat bang cach doc
    luot chuoi "SaveDate >=" don thuan."""
    doan = _ALERTS_SRC[_ALERTS_SRC.find("def get_bravo_kpi_tdv_snapshot"):]
    doan = doan[:doan.find("\ndef ", 10)]
    assert "GROUP BY [EmployeeCode]" in doan
    assert "JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]" in doan


def test_etl_pace_snapshot_co_cte_latest_join_dung_ngay_tung_nguoi():
    doan = _ETL_SRC[_ETL_SRC.find("def get_daily_kpi_pace_snapshot"):]
    doan = doan[:doan.find("\ndef ", 10)]
    assert "GROUP BY [EmployeeCode]" in doan
    assert "JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]" in doan


def test_etl_reconciliation_co_cte_latest_join_dung_ngay_tung_khach():
    doan = _ETL_SRC[_ETL_SRC.find("def get_kpi_revenue_reconciliation"):]
    doan = doan[:doan.find("\ndef ", 10)]
    assert "GROUP BY [CustomerCode]" in doan
    assert "JOIN latest l ON l.[CustomerCode] = f.[CustomerCode] AND l.d = f.[SaveDate]" in doan


# ---------------------------------------------------------------------------------------
# Sinh SQL that (qua SQLAlchemy) va kiem cu phap T-SQL hop le - khong ket noi Bravo
# ---------------------------------------------------------------------------------------

def test_sql_sinh_ra_hop_le_khong_can_ket_noi_bravo():
    """Dung sqlalchemy.text() de compile SQL that (khong execute) - bat loi cu phap f-string/
    ngoac don truoc khi dung tren may 24 that."""
    from sqlalchemy import text
    sql = text(f'''
        WITH latest AS (
            SELECT [EmployeeCode], MAX([SaveDate]) AS d
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] >= {alerts._MONTH_START_OF_LATEST_SNAPSHOT_SQL}
            GROUP BY [EmployeeCode]
        ),
        tdv_target AS (
            SELECT DISTINCT f.[EmployeeCode], f.[AreaCode]
            FROM [FACT_TongHopKhachHang] f
            JOIN latest l ON l.[EmployeeCode] = f.[EmployeeCode] AND l.d = f.[SaveDate]
        )
        SELECT * FROM tdv_target
    ''')
    chuoi = str(sql.compile(compile_kwargs={"literal_binds": False}))
    assert "DATEFROMPARTS" in chuoi
    assert "GROUP BY" in chuoi
