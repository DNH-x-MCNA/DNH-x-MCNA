#!/usr/bin/env bash
# Deploy web chatbot DNH tren Cloud Server tu nhanh master tren GitHub.
#   sudo /opt/dnh-web/repo/deploy/cloud_server/deploy_web.sh              # deploy ban moi nhat cua master
#   sudo /opt/dnh-web/repo/deploy/cloud_server/deploy_web.sh --rollback   # quay ve ban build truoc
#
# Moi ban build vao thu muc rieng (releases/<gio>-<commit>); chi doi symlink /opt/dnh-web/current khi build
# XONG, nen trong luc build web cu van phuc vu binh thuong. Web moi khong len thi tu quay ve ban cu.
# Build khong can khoa: BACKEND_API_URL/BACKEND_API_KEY chi doc luc chay, tu /etc/dnh-web/web.env.
# Than script nam trong main() va "main; exit" o CUNG dong cuoi: bash doc tron dong do truoc khi chay, nen
# git checkout doi chinh file nay giua chung khong lam hong lan dang chay.
set -euo pipefail

APP=/opt/dnh-web
REPO=$APP/repo
RELEASES=$APP/releases
CURRENT=$APP/current
ENV_FILE=/etc/dnh-web/web.env
BRANCH=master
KEEP=3
DEPLOY_USER=dnhdeploy
WEB_USER=dnhweb
BUILD_ENV=(NODE_OPTIONS=--max-old-space-size=1536 NEXT_TELEMETRY_DISABLED=1)

log() { echo "$(date '+%F %T') $*"; }
die() { log "DUNG: $*"; exit 1; }
as_deploy() { sudo -u "$DEPLOY_USER" -H -- "$@"; }
current_target() { readlink -f "$CURRENT" 2>/dev/null || true; }

# Ban build hoan chinh (co danh dau .build-ok), cu -> moi.
built_releases() {
    local d
    for d in "$RELEASES"/*/; do
        [ -f "$d.build-ok" ] && echo "${d%/}"
    done | sort
}

web_ok() {
    local i code
    for i in $(seq 1 45); do
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:3000/ || true)
        [ "$code" = "200" ] && return 0
        sleep 2
    done
    return 1
}

switch_to() {
    ln -sfn "$1" "$CURRENT.tmp"
    mv -Tf "$CURRENT.tmp" "$CURRENT"
    systemctl restart dnh-web
}

backend_check() {
    local url
    url=$(sed -n 's/^BACKEND_API_URL=//p' "$ENV_FILE" | tail -1)
    if [ -z "$url" ]; then
        log "CANH BAO: $ENV_FILE chua co BACKEND_API_URL"
    elif curl -s --max-time 10 "$url/health" | grep -q '"status":"ok"'; then
        log "Backend may 24 tra loi qua duong ham: OK"
    else
        log "CANH BAO: khong goi duoc $url/health - kiem duong ham (sudo wg show) va dich vu backend may 24"
    fi
}

cleanup() {
    local now d
    now=$(current_target)
    for d in $(ls -1d "$RELEASES"/*/ 2>/dev/null | sed 's#/$##' | sort -r | tail -n +$((KEEP + 1))); do
        [ "$d" = "$now" ] && continue
        rm -rf -- "$d"
    done
}

rollback() {
    local now prev
    now=$(current_target)
    prev=$(built_releases | awk -v now="$now" '$0 < now' | tail -1)
    [ -n "$prev" ] || die "khong co ban build truoc de quay ve (dang chay: ${now:-khong co})"
    log "Quay ve $prev (dang chay: ${now:-khong co})"
    switch_to "$prev"
    web_ok || die "ban truoc cung khong len - xem: journalctl -u dnh-web -n 100"
    log "DAT: web chay lai ban $prev"
}

deploy() {
    local sha dest prev
    [ -f "$ENV_FILE" ] || die "chua co $ENV_FILE (tao tu deploy/cloud_server/web.env.mau)"
    if grep -q 'DAN_KHOA_TU_MAY_24' "$ENV_FILE"; then
        die "$ENV_FILE con khoa mau - dan BACKEND_API_KEY that truoc"
    fi

    log "Lay code moi nhat cua $BRANCH..."
    as_deploy git -C "$REPO" fetch --quiet origin "$BRANCH"
    as_deploy git -C "$REPO" checkout --quiet --detach "origin/$BRANCH"
    as_deploy git -C "$REPO" log -1 --oneline
    sha=$(as_deploy git -C "$REPO" rev-parse --short HEAD)
    dest="$RELEASES/$(date +%Y%m%d-%H%M%S)-$sha"
    prev=$(current_target)

    as_deploy mkdir -p "$dest"
    as_deploy bash -c 'git -C "$1" archive HEAD | tar -x -C "$2"' _ "$REPO" "$dest"
    log "Build $sha trong $dest (npm ci + next build + kiem CSS)..."
    if ! as_deploy env "${BUILD_ENV[@]}" bash -c 'cd "$1" && npm ci --no-audit --no-fund && npm run build' _ "$dest"; then
        rm -rf -- "$dest"
        die "build loi - web van chay ban cu (${prev:-chua co ban nao})"
    fi
    # Tien trinh web (dnhweb) chi ghi duoc .next/cache; ma nguon thuoc dnhdeploy.
    as_deploy mkdir -p "$dest/.next/cache"
    chown -R "$WEB_USER:$WEB_USER" "$dest/.next/cache"
    as_deploy touch "$dest/.build-ok"

    switch_to "$dest"
    if ! web_ok; then
        log "LOI: web ban $sha khong len - quay ve ban cu"
        if [ -n "$prev" ] && [ -d "$prev" ]; then
            switch_to "$prev"
            web_ok && log "Da quay ve $prev"
        fi
        rm -rf -- "$dest"
        die "deploy $sha that bai - xem: journalctl -u dnh-web -n 100"
    fi
    log "DAT: web chay ban $sha ($dest)"
    backend_check
    cleanup
}

main() {
    [ "$(id -u)" -eq 0 ] || die "chay bang sudo"
    exec 9>/run/dnh-web-deploy.lock
    flock -n 9 || die "dang co mot lan deploy khac chay"
    case "${1:-}" in
        --rollback) rollback ;;
        "") deploy ;;
        *) die "tham so khong hop le: $1 (chi co --rollback)" ;;
    esac
}

main "$@"; exit
