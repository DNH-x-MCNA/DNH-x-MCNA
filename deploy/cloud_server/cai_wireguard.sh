#!/usr/bin/env bash
# Duong ham WireGuard Cloud Server <-> may 24. CHI chay khi IT DNH xac nhan may 24 duoc DI RA toi IP Cloud
# Server qua UDP 51820 (khong can mo cong nao tu ngoai vao mang DNH: may 24 chu dong noi ra).
#   Buoc 1: sudo bash cai_wireguard.sh
#           -> tao khoa (neu chua co), in KHOA CONG KHAI cua Cloud Server de dan vao may 24.
#   Buoc 2: sudo MAY24_PUBKEY='<Public key WireGuard app tren may 24 hien ra>' bash cai_wireguard.sh
#           -> ghi /etc/wireguard/wg0.conf, mo UDP 51820, bat duong ham.
# Khoa rieng khong bao gio in ra, khong nam trong wg0.conf va khong roi may.
set -euo pipefail

WG_PORT=51820
MAY24_IP=10.88.24.2
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

log() { echo "$(date '+%F %T') $*"; }
die() { log "DUNG: $*"; exit 1; }

main() {
    [ "$(id -u)" -eq 0 ] || die "chay bang sudo"
    command -v wg >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -q wireguard-tools
    install -d -m 0700 /etc/wireguard
    if [ ! -f /etc/wireguard/privatekey ]; then
        (umask 077 && wg genkey > /etc/wireguard/privatekey)
    fi
    wg pubkey < /etc/wireguard/privatekey > /etc/wireguard/publickey
    log "Khoa CONG KHAI cua Cloud Server (dan vao dong PublicKey muc [Peer] tren may 24):"
    cat /etc/wireguard/publickey

    if [ -z "${MAY24_PUBKEY:-}" ]; then
        log "Chua co MAY24_PUBKEY. Tao duong ham tren may 24 theo wireguard/may24.conf.mau, roi chay lai:"
        log "  sudo MAY24_PUBKEY='<Public key cua may 24>' bash $HERE/cai_wireguard.sh"
        exit 0
    fi
    [[ "$MAY24_PUBKEY" =~ ^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=$ ]] || die "MAY24_PUBKEY khong phai khoa WireGuard hop le"
    [ "$MAY24_PUBKEY" != "$(cat /etc/wireguard/publickey)" ] || die "MAY24_PUBKEY dang la khoa cua chinh Cloud Server"

    sed "s#KHOA_CONG_KHAI_MAY_24#$MAY24_PUBKEY#" "$HERE/wireguard/wg0.conf.mau" > /etc/wireguard/wg0.conf.moi
    chmod 0600 /etc/wireguard/wg0.conf.moi
    mv -f /etc/wireguard/wg0.conf.moi /etc/wireguard/wg0.conf

    ufw allow "$WG_PORT/udp" >/dev/null
    # May 24 KHONG can mo ket noi moi toi Cloud Server (chi tra loi web goi vao) -> chan moi ket noi moi
    # tu duong ham, ke ca SSH. Dat len dau vi ufw khop rule theo thu tu.
    ufw status | grep -q 'Anywhere on wg0 .*DENY IN' || ufw insert 1 deny in on wg0 >/dev/null

    systemctl enable wg-quick@wg0 >/dev/null
    systemctl restart wg-quick@wg0
    log "Da bat duong ham. Sau khi may 24 Activate, kiem:"
    log "  sudo wg show wg0 latest-handshakes     (phai co moc thoi gian, khong phai 0)"
    log "  curl -s http://$MAY24_IP:8010/health  (phai ra \"status\":\"ok\")"
}

main "$@"; exit
