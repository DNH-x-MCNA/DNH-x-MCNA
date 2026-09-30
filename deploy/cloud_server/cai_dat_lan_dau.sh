#!/usr/bin/env bash
# Cai dat LAN DAU Cloud Server (Ubuntu 24.04, x86_64) cho web chatbot DNH. Chay lai duoc: buoc da xong thi bo qua.
#
# Can co truoc: ban ghi A chatbot.namhatrading.com da tro ve IP public cua may nay (certbot kiem qua HTTP).
#   sudo apt-get update && sudo apt-get install -y git
#   sudo git clone https://github.com/DNH-x-MCNA/DNH-x-MCNA.git /tmp/dnh-cai
#   sudo EMAIL_LE=<email nhan canh bao het han chung chi> bash /tmp/dnh-cai/deploy/cloud_server/cai_dat_lan_dau.sh
# Chay xong: dan khoa vao /etc/dnh-web/web.env, dung duong ham (cai_wireguard.sh), roi chay deploy_web.sh.
# Lenh certbot o duoi dung --agree-tos: nguoi chay script dong y dieu khoan cua Let's Encrypt.
set -euo pipefail

DOMAIN=chatbot.namhatrading.com
REPO_URL=https://github.com/DNH-x-MCNA/DNH-x-MCNA.git
APP=/opt/dnh-web
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

log() { echo "$(date '+%F %T') $*"; }
die() { log "DUNG: $*"; exit 1; }

check_host() {
    [ "$(id -u)" -eq 0 ] || die "chay bang sudo"
    # shellcheck disable=SC1091
    . /etc/os-release
    [ "${ID:-}" = "ubuntu" ] && [ "${VERSION_ID:-}" = "24.04" ] || die "can Ubuntu 24.04 (dang la ${PRETTY_NAME:-?})"
    [ "$(uname -m)" = "x86_64" ] || die "script chi ho tro x86_64 (dang la $(uname -m))"
    [ -n "${EMAIL_LE:-}" ] || die "dat EMAIL_LE=<email nhan canh bao chung chi> truoc khi chay"
}

install_packages() {
    log "Cai goi he thong..."
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q nginx certbot git curl ufw xz-utils unattended-upgrades
    # Tu cai ban va bao mat hang ngay (may phoi ra internet).
    printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
        > /etc/apt/apt.conf.d/20auto-upgrades
}

# Node 22 LTS (ban va loi moi nhat) tu nodejs.org, kiem SHA256. Goi apt cua Ubuntu 24.04 la Node 18 - Next 16 khong chay.
install_node() {
    if command -v node >/dev/null 2>&1 && node -v | grep -q '^v22\.'; then
        log "Node $(node -v) da co"
        return
    fi
    local base=https://nodejs.org/dist/latest-v22.x tmp file dir
    tmp=$(mktemp -d)
    curl -fsSL "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
    file=$(grep -o 'node-v22\.[0-9.]*-linux-x64\.tar\.xz' "$tmp/SHASUMS256.txt" | head -1)
    [ -n "$file" ] || die "khong tim thay goi Node 22 linux-x64 trong SHASUMS256.txt"
    curl -fsSL "$base/$file" -o "$tmp/$file"
    (cd "$tmp" && grep "  $file\$" SHASUMS256.txt | sha256sum -c -) || die "checksum goi Node khong khop"
    mkdir -p /usr/local/lib/nodejs
    tar -xJf "$tmp/$file" -C /usr/local/lib/nodejs
    dir=/usr/local/lib/nodejs/${file%.tar.xz}
    for b in node npm npx; do ln -sfn "$dir/bin/$b" "/usr/local/bin/$b"; done
    rm -rf "$tmp"
    log "Da cai Node $(node -v)"
}

setup_users_dirs() {
    mkdir -p "$APP"
    id dnhweb >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin dnhweb
    id dnhdeploy >/dev/null 2>&1 || useradd --system --create-home --home-dir "$APP/deploy-home" \
        --shell /usr/sbin/nologin dnhdeploy
    chmod 0700 "$APP/deploy-home"
    install -d -m 0755 -o dnhdeploy -g dnhdeploy "$APP/repo" "$APP/releases"
    if [ ! -d "$APP/repo/.git" ]; then
        log "Clone repo vao $APP/repo..."
        sudo -u dnhdeploy -H git clone --quiet "$REPO_URL" "$APP/repo"
    fi
    install -d -m 0750 -o root -g dnhweb /etc/dnh-web
    if [ ! -f /etc/dnh-web/web.env ]; then
        install -m 0640 -o root -g dnhweb "$HERE/web.env.mau" /etc/dnh-web/web.env
        log "Da tao /etc/dnh-web/web.env tu mau - PHAI dan BACKEND_API_KEY that truoc khi deploy"
    fi
}

setup_swap() {
    # May 2 GB RAM: next build can them bo nho, thieu swap thi build co the bi kill giua chung.
    if swapon --show | grep -q .; then
        return
    fi
    log "Tao swap 2 GB..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
}

setup_firewall() {
    local p
    ufw default deny incoming >/dev/null
    ufw default allow outgoing >/dev/null
    # Mo DUNG cong SSH dang dung (khong mac dinh 22) de khong tu khoa minh ngoai khi bat ufw.
    for p in $(sshd -T 2>/dev/null | awk '/^port /{print $2}'); do ufw allow "$p/tcp" >/dev/null; done
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw --force enable >/dev/null
    log "Tuong lua: $(ufw status | tr '\n' ' ')"
}

check_dns() {
    local ip
    ip=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}')
    [ -n "$ip" ] || die "$DOMAIN chua co ban ghi A - nho IT DNH them ban ghi tro ve IP may nay roi chay lai"
    if ! hostname -I | tr ' ' '\n' | grep -qx "$ip"; then
        log "CANH BAO: $DOMAIN -> $ip, khong trung IP nao tren card mang may nay (co the do NAT cua Mat Bao)."
        log "Neu $ip khong phai IP public cua may nay thi certbot se loi - sua DNS truoc."
    fi
}

setup_nginx_tls() {
    install -d -m 0755 /var/www/letsencrypt
    rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/dnh-acme-tam.conf
    if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        check_dns
        log "Lay chung chi Let's Encrypt cho $DOMAIN..."
        install -m 0644 "$HERE/nginx/acme-tam.conf" /etc/nginx/sites-available/dnh-acme-tam.conf
        ln -sfn /etc/nginx/sites-available/dnh-acme-tam.conf /etc/nginx/sites-enabled/dnh-acme-tam.conf
        nginx -t
        systemctl reload-or-restart nginx
        certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" \
            --email "$EMAIL_LE" --agree-tos --no-eff-email --non-interactive
        rm -f /etc/nginx/sites-enabled/dnh-acme-tam.conf
    fi
    install -m 0644 "$HERE/nginx/$DOMAIN.conf" "/etc/nginx/sites-available/$DOMAIN.conf"
    ln -sfn "/etc/nginx/sites-available/$DOMAIN.conf" "/etc/nginx/sites-enabled/$DOMAIN.conf"
    nginx -t
    systemctl reload-or-restart nginx
    # Gia han: certbot.timer cua goi Ubuntu; nap lai nginx sau moi lan gia han thanh cong.
    install -d /etc/letsencrypt/renewal-hooks/deploy
    printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    systemctl enable --now certbot.timer >/dev/null 2>&1 || log "CANH BAO: khong bat duoc certbot.timer - kiem gia han tay"
}

setup_service() {
    install -m 0644 "$HERE/systemd/dnh-web.service" /etc/systemd/system/dnh-web.service
    systemctl daemon-reload
    # Chi bat khi khoi dong may; lan chay dau do deploy_web.sh (can /opt/dnh-web/current).
    systemctl enable dnh-web >/dev/null
}

main() {
    check_host
    install_packages
    install_node
    setup_users_dirs
    setup_swap
    setup_firewall
    setup_nginx_tls
    setup_service
    log "XONG phan cai dat. Con lai:"
    log "  1. sudo nano /etc/dnh-web/web.env  -> dan BACKEND_API_KEY (khong dan vao chat/email)"
    log "  2. Duong ham toi may 24: sudo bash $APP/repo/deploy/cloud_server/cai_wireguard.sh"
    log "  3. sudo $APP/repo/deploy/cloud_server/deploy_web.sh"
}

main "$@"; exit
