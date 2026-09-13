import sqlite3

from scripts import chuan_bi_tai_khoan_uat as uat

auth = uat.auth


def _auth_db(tmp_path, monkeypatch):
    path = tmp_path / "auth.db"
    monkeypatch.setattr(auth, "DB_PATH", str(path))
    auth.init_schema()
    return path


def _tao(username, role, scope_value=None, employee_code=None, scope_channel=None,
         last_login_at=None, is_active=1):
    auth.create_user(username, "mk-cu-123", username, role, scope_value, employee_code,
                     scope_channel)
    with sqlite3.connect(auth.DB_PATH) as conn:
        conn.execute("UPDATE users SET last_login_at=?, is_active=? WHERE username=?",
                     (last_login_at, is_active, username))


def test_giam_doc_mien_bi_ep_thanh_qlv_duoc_bao_la_dang_bi_chan(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    # Dung hinh 13/08/2026: loi khoi dong ep hung.le (TP Mien Trung) thanh qlv, mat ma NV.
    _tao("hung.le", "qlv", "MT")
    _tao("tu.pham", "qlv", "MB", "MBKV2")
    bo = [m for m in uat.BO_TEST if m["username"] in {"hung.le", "tu.pham", "tung.tran"}]

    ket_qua = {m["username"]: (tt, ct) for m, _, tt, ct in
               uat.danh_gia(bo, uat._doc(path, [m["username"] for m in bo]))}

    assert ket_qua["tu.pham"] == ("DUNG", "")
    assert ket_qua["hung.le"][0] == "SAI_CAU_HINH"
    assert "403" in ket_qua["hung.le"][1] and "mã NV" in ket_qua["hung.le"][1]
    assert ket_qua["tung.tran"][0] == "KHONG_TON_TAI"


def test_tai_khoan_bi_khoa_khong_duoc_tinh_la_san_sang(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("danh.nguyen", "qlv", "MN", "TM23100148", is_active=0)
    bo = [m for m in uat.BO_TEST if m["username"] == "danh.nguyen"]

    (_, _, trang_thai, _), = uat.danh_gia(bo, uat._doc(path, ["danh.nguyen"]))

    assert trang_thai == "BI_KHOA"


def test_sua_pham_vi_gan_lai_dung_vai_tro_va_het_bi_chan(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("hung.le", "qlv", "MT")
    _tao("thuy.nguyen", "qlv", None, None, "OTC")
    bo = [m for m in uat.BO_TEST if m["username"] in {"hung.le", "thuy.nguyen"}]
    ten = [m["username"] for m in bo]

    da_sua = uat.sua_pham_vi(uat.danh_gia(bo, uat._doc(path, ten)))

    assert sorted(da_sua) == ["hung.le", "thuy.nguyen"]
    sau = uat._doc(path, ten)
    assert (sau["hung.le"]["role"], sau["hung.le"]["scope_value"],
            sau["hung.le"]["employee_code"]) == ("regional_director", "MT", None)
    assert (sau["thuy.nguyen"]["scope_value"], sau["thuy.nguyen"]["employee_code"],
            sau["thuy.nguyen"]["scope_channel"]) == ("MB", "TM25010183", None)
    assert all(tt == "DUNG" for _, _, tt, _ in uat.danh_gia(bo, sau))


def test_cap_mk_tu_choi_tai_khoan_da_dang_nhap_va_ngoai_bo_test(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("thuy.nguyen2", "regional_director", "MB", last_login_at="2026-08-13T08:58:00")
    _tao("vui.hoangthi", "regional_director", scope_channel="OTC")
    hien_tai = uat._doc(path, ["thuy.nguyen2", "vui.hoangthi"])

    da_cap, tu_choi = uat.cap_mat_khau(["thuy.nguyen2", "vui.hoangthi"], hien_tai)

    assert da_cap == []
    ly_do = dict(tu_choi)
    assert "đã từng đăng nhập" in ly_do["thuy.nguyen2"]
    assert "không nằm trong bộ test" in ly_do["vui.hoangthi"]
    assert "error" not in auth.verify_login("thuy.nguyen2", "mk-cu-123")
    assert "error" not in auth.verify_login("vui.hoangthi", "mk-cu-123")


def test_cap_mk_dat_mat_khau_moi_thu_hoi_phien_cu_va_bat_doi_mk(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("danh.nguyen", "qlv", "MN", "TM23100148")
    # Co phien = da dang nhap (create_session ghi last_login_at), nen phai kem co cho phep.
    token_cu = auth.create_session(auth.get_user_by_email_or_username("danh.nguyen")["id"])
    hien_tai = uat._doc(path, ["danh.nguyen"])
    assert uat.cap_mat_khau(["danh.nguyen"], hien_tai)[0] == []

    da_cap, tu_choi = uat.cap_mat_khau(["danh.nguyen"], hien_tai, ke_ca_da_dang_nhap=True)

    assert tu_choi == []
    (username, mat_khau), = da_cap
    assert username == "danh.nguyen" and len(mat_khau) == 12
    assert auth.verify_login("danh.nguyen", "mk-cu-123").get("error") == "wrong_password"
    moi = auth.verify_login("danh.nguyen", mat_khau)
    assert "error" not in moi and moi["must_change_password"]
    assert auth.get_user_by_session(token_cu) is None


def test_tao_moi_chi_tao_tai_khoan_test_va_khong_tao_lai_tai_khoan_that(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    ten = [m["username"] for m in uat.BO_TEST]

    da_tao = uat.tao_moi(uat.danh_gia(uat.BO_TEST, uat._doc(path, ten)))

    # hung.le, tu.pham, dnh_otc... thieu trong DB nay nhung KHONG duoc tu tao: la tai khoan da co.
    moi = ["chosi.mb", "chosi.mn", "dnh_etc", "head.mt"]
    assert sorted(u for u, _ in da_tao) == moi
    sau = uat._doc(path, ten)
    assert sorted(sau) == moi
    # Kenh MT (Modern Trade) o Mien Nam - khong phai vung "MT" Mien Trung.
    assert (sau["head.mt"]["role"], sau["head.mt"]["scope_value"],
            sau["head.mt"]["employee_code"]) == ("qlv", "MN", "MN1")
    assert (sau["dnh_etc"]["role"], sau["dnh_etc"]["scope_value"],
            sau["dnh_etc"]["scope_channel"]) == ("regional_director", None, "ETC")
    for username, mat_khau in da_tao:
        dang_nhap = auth.verify_login(username, mat_khau)
        assert "error" not in dang_nhap and dang_nhap["must_change_password"]
        assert uat._ly_do_bi_chan(*uat._chuan_hoa(
            sau[username]["role"], sau[username]["scope_value"],
            sau[username]["employee_code"], sau[username]["scope_channel"])) is None


def test_tao_moi_bo_qua_tai_khoan_test_da_co(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("head.mt", "qlv", "MN", "MN1")
    bo = [m for m in uat.BO_TEST if m.get("tao_moi")]

    da_tao = uat.tao_moi(uat.danh_gia(bo, uat._doc(path, [m["username"] for m in bo])))

    assert sorted(u for u, _ in da_tao) == ["chosi.mb", "chosi.mn", "dnh_etc"]
    assert "error" not in auth.verify_login("head.mt", "mk-cu-123")


def test_dnh_otc_bi_chan_duoc_sua_thanh_giam_doc_kenh_otc(tmp_path, monkeypatch):
    path = _auth_db(tmp_path, monkeypatch)
    _tao("dnh_otc", "qlv", scope_channel="OTC")  # hinh dang trong danh sach 13/08
    bo = [m for m in uat.BO_TEST if m["username"] == "dnh_otc"]

    (_, _, trang_thai, chi_tiet), = uat.danh_gia(bo, uat._doc(path, ["dnh_otc"]))
    assert trang_thai == "SAI_CAU_HINH" and "403" in chi_tiet

    uat.sua_pham_vi(uat.danh_gia(bo, uat._doc(path, ["dnh_otc"])))
    sau = uat._doc(path, ["dnh_otc"])["dnh_otc"]
    assert (sau["role"], sau["scope_value"], sau["scope_channel"]) == ("regional_director", None, "OTC")


def test_quy_tac_chan_khop_voi_main():
    assert uat._ly_do_bi_chan("qlv", "MB", None, None)
    assert uat._ly_do_bi_chan("regional_director", None, None, None)
    assert uat._ly_do_bi_chan("regional_director", "MB", "MBKV2", None)
    assert uat._ly_do_bi_chan("c_level", None, None, "OTC")
    assert uat._ly_do_bi_chan("admin_ops", None, None, None)
    assert uat._ly_do_bi_chan("regional_director", None, None, "OTC") is None
    assert uat._ly_do_bi_chan("qlv", "MN", "TM23100148", None) is None
