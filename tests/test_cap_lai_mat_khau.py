import json

from scripts import cap_lai_mat_khau as reset

auth = reset.auth


def _chuan_bi(tmp_path, monkeypatch):
    db = tmp_path / "auth.db"
    monkeypatch.setattr(auth, "DB_PATH", str(db))
    auth.init_schema()
    auth.create_user("tu.pham", "mk-cu-123", "Phạm Xuân Tú", "qlv", "MB", "MBKV2")
    auth.create_user("dnh", "mk-cu-123", "DNH C-Level", "c_level")
    return db, tmp_path / "audit_log.jsonl"


def _mat_khau_in_ra(capsys):
    dong = [d for d in capsys.readouterr().out.splitlines() if d.startswith("  tu.pham") or
            d.startswith("  dnh")]
    return dong[-1].split()[-1]


def test_cap_mk_tam_thu_hoi_phien_ghi_audit_khong_lo_mat_khau(tmp_path, monkeypatch, capsys):
    db, audit = _chuan_bi(tmp_path, monkeypatch)
    token_cu = auth.create_session(auth.get_user_by_email_or_username("tu.pham")["id"])

    ma = reset.main(["tu.pham", "--db", str(db), "--audit-log", str(audit), "--dong-y"])

    assert ma == 0
    mat_khau = _mat_khau_in_ra(capsys)
    assert len(mat_khau) == 12
    assert auth.verify_login("tu.pham", "mk-cu-123").get("error") == "wrong_password"
    moi = auth.verify_login("tu.pham", mat_khau)
    assert "error" not in moi and moi["must_change_password"]
    assert auth.get_user_by_session(token_cu) is None
    dong_audit = audit.read_text(encoding="utf-8").splitlines()
    assert len(dong_audit) == 1
    assert "tu.pham" in json.loads(dong_audit[0])["question"]
    assert mat_khau not in dong_audit[0]


def test_tai_khoan_dac_quyen_can_co_rieng(tmp_path, monkeypatch, capsys):
    db, audit = _chuan_bi(tmp_path, monkeypatch)
    chung = ["--db", str(db), "--audit-log", str(audit), "--dong-y"]

    assert reset.main(["dnh"] + chung) == 2
    assert "error" not in auth.verify_login("dnh", "mk-cu-123")
    assert not audit.exists()

    assert reset.main(["dnh", "--tai-khoan-dac-quyen"] + chung) == 0
    assert "error" not in auth.verify_login("dnh", _mat_khau_in_ra(capsys))


def test_go_sai_username_xac_nhan_thi_khong_doi_gi(tmp_path, monkeypatch):
    db, audit = _chuan_bi(tmp_path, monkeypatch)

    ma = reset.main(["tu.pham", "--db", str(db), "--audit-log", str(audit)],
                    nhap=lambda _: "tu.phan")

    assert ma == 2
    assert "error" not in auth.verify_login("tu.pham", "mk-cu-123")
    assert not audit.exists()


def test_khong_tim_thay_tai_khoan(tmp_path, monkeypatch):
    db, audit = _chuan_bi(tmp_path, monkeypatch)

    assert reset.main(["khong.co", "--db", str(db), "--audit-log", str(audit), "--dong-y"]) == 2
    assert not audit.exists()
