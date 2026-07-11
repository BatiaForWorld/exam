#!/usr/bin/env bash
set -Eeuo pipefail

# Self-contained security bootstrap for a Debian/Ubuntu VPS.
# Installs nftables, fail2ban, WireGuard tools and fwknop, then enforces SSH key-only login.
# Run as root. Recommended first run over an already working SSH key session.

SSH_PORT="${SSH_PORT:-22}"
WG_PORT="${WG_PORT:-51820}"
FWKNOP_PORT="${FWKNOP_PORT:-62201}"
WG_IF="${WG_IF:-wg0}"
WAN_IF="${WAN_IF:-}"
ADMIN_CIDR="${ADMIN_CIDR:-}"
INSTALL_USER="${INSTALL_USER:-root}"
SSH_PUBLIC_KEY="${SSH_PUBLIC_KEY:-}"
ENABLE_FWKNOP="${ENABLE_FWKNOP:-1}"
ENABLE_WIREGUARD_PLACEHOLDER="${ENABLE_WIREGUARD_PLACEHOLDER:-1}"
THREAT_SET_TIMEOUT="${THREAT_SET_TIMEOUT:-7d}"
MAIL_HOSTNAME="${MAIL_HOSTNAME:-$(hostname -f 2>/dev/null || hostname)}"

log() {
    printf '[security-bootstrap] %s\n' "$*"
}

fail() {
    printf '[security-bootstrap] ERROR: %s\n' "$*" >&2
    exit 1
}

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "run as root"
    fi
}

backup_file() {
    local path="$1"
    if [ -e "$path" ] && [ ! -e "$path.bootstrap-backup" ]; then
        cp -a "$path" "$path.bootstrap-backup"
    fi
}

validate_public_key_string() {
    local key_string="$1"
    local key_tmp

    key_tmp="$(mktemp)"
    printf '%s\n' "$key_string" > "$key_tmp"
    if ! ssh-keygen -l -f "$key_tmp" >/dev/null 2>&1; then
        rm -f "$key_tmp"
        fail "SSH_PUBLIC_KEY is not a valid public key; do not use the README placeholder"
    fi
    rm -f "$key_tmp"
}

detect_wan_if() {
    if [ -n "$WAN_IF" ]; then
        return
    fi
    WAN_IF="$(ip route show default 2>/dev/null | awk 'NR == 1 { for (i = 1; i <= NF; i++) if ($i == "dev") { print $(i + 1); exit } }')"
    if [ -z "$WAN_IF" ]; then
        fail "cannot detect WAN_IF; rerun with WAN_IF=eth0"
    fi
}

detect_admin_cidr() {
    if [ -n "$ADMIN_CIDR" ]; then
        return
    fi
    local client_ip="${SSH_CLIENT%% *}"
    if [ -z "$client_ip" ] && [ -n "${SSH_CONNECTION:-}" ]; then
        client_ip="${SSH_CONNECTION%% *}"
    fi
    if [ -n "$client_ip" ]; then
        case "$client_ip" in
            *:*) ADMIN_CIDR="$client_ip/128" ;;
            *) ADMIN_CIDR="$client_ip/32" ;;
        esac
        return
    fi
    fail "cannot detect current SSH client; rerun with ADMIN_CIDR=YOUR_IP/32"
}

validate_admin_cidr() {
    case "$ADMIN_CIDR" in
        *:*) fail "IPv6-only ADMIN_CIDR is not enough for this script; provide an IPv4 ADMIN_CIDR too" ;;
        */*) ;;
        *) ADMIN_CIDR="$ADMIN_CIDR/32" ;;
    esac
}

ensure_apt() {
    if ! command -v apt-get >/dev/null 2>&1; then
        fail "this installer supports Debian/Ubuntu with apt-get"
    fi
    export DEBIAN_FRONTEND=noninteractive
    printf 'postfix postfix/mailname string %s\n' "$MAIL_HOSTNAME" | debconf-set-selections || true
    printf 'postfix postfix/main_mailer_type string Internet Site\n' | debconf-set-selections || true
    apt-get update
    apt-get install -y --no-install-recommends \
        ca-certificates curl gawk iproute2 cron logrotate openssl rsyslog \
        openssh-server nftables fail2ban fwknop-server wireguard-tools \
        nginx postfix dovecot-core dovecot-imapd dovecot-lmtpd dovecot-sieve dovecot-managesieved

    systemctl enable --now rsyslog
}

write_postfix_abuse_controls() {
    install -d -m 0755 /etc/postfix
    touch /etc/postfix/sasl_abuse_blocklist
    chmod 0644 /etc/postfix/sasl_abuse_blocklist
    postmap /etc/postfix/sasl_abuse_blocklist

    postconf -e "smtpd_recipient_restrictions = check_sasl_access hash:/etc/postfix/sasl_abuse_blocklist, reject_unknown_recipient_domain, reject_non_fqdn_recipient, reject_invalid_helo_hostname, reject_unauth_destination"
    postconf -e "smtpd_relay_restrictions = permit_mynetworks, permit_sasl_authenticated, reject_unauth_destination"
    postconf -e "smtpd_sasl_authenticated_header = yes"
    postconf -e "smtpd_tls_auth_only = yes"
    postconf -e "maillog_file = /var/log/mail.log"

    cat > /usr/local/sbin/postfix-abuse-user <<'EOF'
#!/bin/sh
set -eu

MAP_FILE="${MAP_FILE:-/etc/postfix/sasl_abuse_blocklist}"
POSTMAP_BIN="${POSTMAP_BIN:-/usr/sbin/postmap}"
POSTFIX_BIN="${POSTFIX_BIN:-/usr/sbin/postfix}"

usage() {
    echo "Usage: $0 block USER@example.com [reason] | unblock USER@example.com | list | rebuild" >&2
    exit 2
}

command="${1:-}"
user="${2:-}"
reason="${3:-suspected outbound mail abuse}"

normalize_user() {
    printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]'
}

remove_user_line() {
    awk -v user="$1" '$1 != user { print }' "$MAP_FILE" 2>/dev/null || true
}

rebuild() {
    "$POSTMAP_BIN" "$MAP_FILE"
    "$POSTFIX_BIN" reload >/dev/null 2>&1 || true
}

case "$command" in
    block)
        [ -n "$user" ] || usage
        user="$(normalize_user "$user")"
        tmp="$(mktemp)"
        remove_user_line "$user" > "$tmp"
        printf '%s REJECT Account temporarily disabled: %s\n' "$user" "$reason" >> "$tmp"
        cat "$tmp" > "$MAP_FILE"
        rm -f "$tmp"
        rebuild
        ;;
    unblock)
        [ -n "$user" ] || usage
        user="$(normalize_user "$user")"
        tmp="$(mktemp)"
        remove_user_line "$user" > "$tmp"
        cat "$tmp" > "$MAP_FILE"
        rm -f "$tmp"
        rebuild
        ;;
    list)
        cat "$MAP_FILE"
        ;;
    rebuild)
        rebuild
        ;;
    *)
        usage
        ;;
esac
EOF
    chmod 0750 /usr/local/sbin/postfix-abuse-user
    systemctl enable postfix
    systemctl reload postfix || systemctl restart postfix
}

prepare_log_files() {
    install -d -m 0755 /var/log/nginx
    cat > /etc/rsyslog.d/30-fwknopd.conf <<'EOF'
if $programname == 'fwknopd' then /var/log/fwknopd.log
& stop
EOF
    systemctl restart rsyslog

    touch /var/log/auth.log \
        /var/log/mail.log \
        /var/log/dovecot.log \
        /var/log/nginx/access.log \
        /var/log/nginx/error.log \
        /var/log/fwknopd.log \
        /var/log/fail2ban.log

    if getent group adm >/dev/null 2>&1; then
        chgrp adm /var/log/auth.log /var/log/mail.log /var/log/dovecot.log /var/log/fwknopd.log /var/log/fail2ban.log || true
        chmod 0640 /var/log/auth.log /var/log/mail.log /var/log/dovecot.log /var/log/fwknopd.log /var/log/fail2ban.log || true
    fi
    chmod 0644 /var/log/nginx/access.log /var/log/nginx/error.log || true
}

install_ssh_key() {
    local home_dir key_file target_user
    target_user="$INSTALL_USER"

    if ! id "$target_user" >/dev/null 2>&1; then
        fail "INSTALL_USER=$target_user does not exist"
    fi

    home_dir="$(getent passwd "$target_user" | cut -d: -f6)"
    [ -n "$home_dir" ] || fail "cannot determine home directory for $target_user"

    install -d -m 0700 -o "$target_user" -g "$target_user" "$home_dir/.ssh"
    key_file="$home_dir/.ssh/authorized_keys"
    touch "$key_file"
    chown "$target_user:$target_user" "$key_file"
    chmod 0600 "$key_file"

    if [ -n "$SSH_PUBLIC_KEY" ]; then
        validate_public_key_string "$SSH_PUBLIC_KEY"
        if ! grep -qxF "$SSH_PUBLIC_KEY" "$key_file"; then
            printf '%s\n' "$SSH_PUBLIC_KEY" >> "$key_file"
        fi
    fi

    if [ ! -s "$key_file" ]; then
        fail "no SSH key found for $target_user; set SSH_PUBLIC_KEY='ssh-ed25519 ...' before running"
    fi
}

harden_sshd() {
    install -d -m 0755 /etc/ssh/sshd_config.d
    cat > /etc/ssh/sshd_config.d/10-key-only.conf <<EOF
Port $SSH_PORT
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
AuthenticationMethods publickey
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

    sshd -t
    systemctl reload ssh || systemctl reload sshd
}

write_nftables() {
    backup_file /etc/nftables.conf
    install -d -m 0750 /etc/nftables.d

    cat > /etc/nftables.conf <<EOF
#!/usr/sbin/nft -f
flush ruleset

define WAN_IF = "$WAN_IF"
define WG_IF = "$WG_IF"
define SSH_PORT = $SSH_PORT
define WG_PORT = $WG_PORT
define FWKNOP_PORT = $FWKNOP_PORT

table inet filter {
    set trusted_admin_v4 {
        type ipv4_addr
        flags interval
        elements = { $ADMIN_CIDR, 10.8.0.0/24 }
    }

    set fail2ban_v4 {
        type ipv4_addr
        flags timeout
    }

    set fail2ban_v6 {
        type ipv6_addr
        flags timeout
    }

    set threat_v4 {
        type ipv4_addr
        flags interval,timeout
    }

    set threat_v6 {
        type ipv6_addr
        flags interval,timeout
    }

    set fwknop_ssh_v4 {
        type ipv4_addr
        flags timeout
    }

    set fwknop_ssh_v6 {
        type ipv6_addr
        flags timeout
    }

    chain input {
        type filter hook input priority filter; policy drop;

        iifname "lo" accept
        ct state invalid drop
        ct state established,related accept

        ip saddr @threat_v4 drop
        ip6 saddr @threat_v6 drop
        ip saddr @fail2ban_v4 drop
        ip6 saddr @fail2ban_v6 drop

        icmp type { echo-request, destination-unreachable, time-exceeded, parameter-problem } limit rate 10/second burst 20 packets accept
        icmpv6 type { echo-request, destination-unreachable, packet-too-big, time-exceeded, parameter-problem, nd-neighbor-solicit, nd-neighbor-advert, nd-router-advert } limit rate 10/second burst 20 packets accept

        udp dport \$WG_PORT limit rate 20/minute burst 40 packets accept
        udp dport \$FWKNOP_PORT limit rate 10/minute burst 20 packets accept

        iifname \$WG_IF tcp dport { \$SSH_PORT, 143, 4190 } accept
        tcp dport \$SSH_PORT ip saddr @trusted_admin_v4 ct state new limit rate 6/minute burst 10 packets accept
        tcp dport \$SSH_PORT ip saddr @fwknop_ssh_v4 ct state new accept
        tcp dport \$SSH_PORT ip6 saddr @fwknop_ssh_v6 ct state new accept

        tcp dport { 25, 80, 443, 465, 587, 993 } ct state new limit rate 120/minute burst 240 packets accept
        tcp dport { 143, 4190 } ip saddr @trusted_admin_v4 accept

        log prefix "nft-input-drop " flags all counter drop
    }

    chain forward {
        type filter hook forward priority filter; policy drop;
        ct state invalid drop
        ct state established,related accept
        iifname \$WG_IF accept
    }

    chain output {
        type filter hook output priority filter; policy accept;
    }
}
EOF

    nft -c -f /etc/nftables.conf
    systemctl enable --now nftables
    systemctl reload nftables
}

write_fail2ban_helper() {
    cat > /usr/local/sbin/fail2ban-nft-e-mail.sh <<'EOF'
#!/bin/sh
set -eu

NFT_BIN="${NFT_BIN:-/usr/sbin/nft}"
FAMILY="${FAMILY:-inet}"
TABLE="${TABLE:-filter}"
SET_V4="${SET_V4:-fail2ban_v4}"
SET_V6="${SET_V6:-fail2ban_v6}"

usage() {
    echo "Usage: $0 check|ban|unban [ip] [bantime]" >&2
    exit 2
}

command="${1:-}"
ip="${2:-}"
bantime="${3:-1h}"

set_for_ip() {
    case "$1" in
        *:*) printf '%s\n' "$SET_V6" ;;
        *) printf '%s\n' "$SET_V4" ;;
    esac
}

case "$command" in
    check)
        "$NFT_BIN" list set "$FAMILY" "$TABLE" "$SET_V4" >/dev/null
        "$NFT_BIN" list set "$FAMILY" "$TABLE" "$SET_V6" >/dev/null
        ;;
    ban)
        [ -n "$ip" ] || usage
        set_name="$(set_for_ip "$ip")"
        "$NFT_BIN" add element "$FAMILY" "$TABLE" "$set_name" "{ $ip timeout $bantime }"
        ;;
    unban)
        [ -n "$ip" ] || usage
        set_name="$(set_for_ip "$ip")"
        "$NFT_BIN" delete element "$FAMILY" "$TABLE" "$set_name" "{ $ip }" 2>/dev/null || true
        ;;
    *)
        usage
        ;;
esac
EOF
    chmod 0750 /usr/local/sbin/fail2ban-nft-e-mail.sh
}

write_fail2ban() {
    install -d -m 0755 /etc/fail2ban/filter.d /etc/fail2ban/action.d /etc/fail2ban/jail.d

    cat > /etc/fail2ban/action.d/nftables-e-mail.conf <<'EOF'
[Definition]
actionstart = /usr/local/sbin/fail2ban-nft-e-mail.sh check
actionstop =
actioncheck = /usr/local/sbin/fail2ban-nft-e-mail.sh check
actionban = /usr/local/sbin/fail2ban-nft-e-mail.sh ban <ip> <bantime>
actionunban = /usr/local/sbin/fail2ban-nft-e-mail.sh unban <ip>
EOF

    cat > /etc/fail2ban/filter.d/fwknop.conf <<'EOF'
[Definition]
failregex = ^.*fwknopd(?:\[[0-9]+\])?: .*?(?:Invalid|replay|Replay|digest|HMAC|decrypt|spoof|unauthorized|not a valid SPA|No access|not allowed).*?(?:from|SRC=|source IP:?)\s*<HOST>.*$
            ^.*fwknopd(?:\[[0-9]+\])?: .*?<HOST>.*?(?:Invalid|replay|Replay|digest|HMAC|decrypt|spoof|unauthorized|not a valid SPA|No access|not allowed).*$
ignoreregex =
EOF

    cat > /etc/fail2ban/filter.d/nginx-e-mail-abuse.conf <<'EOF'
[Definition]
failregex = ^<HOST> - .* "(?:GET|POST|HEAD|PUT|DELETE|OPTIONS) /(?:\.env|\.git|wp-admin|wp-login\.php|xmlrpc\.php|phpmyadmin|pma|adminer|cgi-bin|vendor|composer\.(?:json|lock)|server-status|boaform|HNAP1|shell|hudson|jenkins|actuator|debug|api/v[0-9]+/debug)[^ ]* HTTP/[^\"]+" (?:400|401|403|404|405|444) .*$
            ^<HOST> - .* "[^\"]*" 429 .*$
            ^<HOST> - .* "(?:GET|POST|HEAD) /(?:login|register|forgot-password|reset)/?[^ ]* HTTP/[^\"]+" (?:400|401|403|429) .*$
ignoreregex =
EOF

    cat > /etc/fail2ban/filter.d/postfix-rbl-hard.conf <<'EOF'
[Definition]
failregex = ^.*postfix/(?:smtpd|submission/smtpd|smtps/smtpd)\[[0-9]+\]: NOQUEUE: reject: RCPT from \S+\[<HOST>\]: 554 5\.7\.1 Service unavailable; Client host \[<HOST>\] blocked using .*$
            ^.*postfix/(?:smtpd|submission/smtpd|smtps/smtpd)\[[0-9]+\]: NOQUEUE: reject: RCPT from \S+\[<HOST>\]: 450 4\.7\.1 Client host rejected: cannot find your reverse hostname.*$
            ^.*postfix/(?:smtpd|submission/smtpd|smtps/smtpd)\[[0-9]+\]: warning: \S+\[<HOST>\]: SASL (?:LOGIN|PLAIN) authentication failed: .*$
ignoreregex =
EOF

    cat > /etc/fail2ban/filter.d/dovecot-hard.conf <<'EOF'
[Definition]
failregex = ^.*dovecot(?:\[[0-9]+\])?: .*auth.*(?:failed|Failure|unknown user|invalid credentials).*rip=<HOST>.*$
            ^.*dovecot(?:\[[0-9]+\])?: .*imap-login: Disconnected: (?:Auth failed|Aborted login).*rip=<HOST>.*$
ignoreregex =
EOF

    cat > /etc/fail2ban/jail.d/e-mail.local <<EOF
[DEFAULT]
backend = auto
usedns = warn
ignoreip = 127.0.0.1/8 ::1 $ADMIN_CIDR 10.8.0.0/24
banaction = nftables-e-mail
banaction_allports = nftables-e-mail
findtime = 10m
bantime = 2h
maxretry = 4
bantime.increment = true
bantime.factor = 2
bantime.maxtime = 14d
bantime.rndtime = 10m

[sshd]
enabled = true
mode = aggressive
port = $SSH_PORT
logpath = /var/log/auth.log
maxretry = 3
findtime = 10m
bantime = 12h

[sshd-ddos]
enabled = true
filter = sshd[mode=aggressive]
port = $SSH_PORT
logpath = /var/log/auth.log
maxretry = 8
findtime = 2m
bantime = 24h

[fwknop]
enabled = true
filter = fwknop
port = $FWKNOP_PORT
protocol = udp
logpath = /var/log/fwknopd.log
maxretry = 2
findtime = 1h
bantime = 7d

[postfix-sasl]
enabled = true
port = smtp,submissions,submission,imap,imaps,sieve
logpath = /var/log/mail.log
maxretry = 3
findtime = 15m
bantime = 12h

[postfix-rbl-hard]
enabled = true
filter = postfix-rbl-hard
port = smtp,submissions,submission
logpath = /var/log/mail.log
maxretry = 4
findtime = 30m
bantime = 24h

[postfix]
enabled = true
port = smtp,submissions,submission
logpath = /var/log/mail.log
maxretry = 5
findtime = 30m
bantime = 12h

[dovecot]
enabled = true
port = imap,imaps,sieve
logpath = /var/log/dovecot.log
maxretry = 4
findtime = 15m
bantime = 12h

[dovecot-hard]
enabled = true
filter = dovecot-hard
port = imap,imaps,sieve
logpath = /var/log/dovecot.log
maxretry = 3
findtime = 15m
bantime = 24h

[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3
findtime = 10m
bantime = 12h

[nginx-botsearch]
enabled = true
port = http,https
logpath = /var/log/nginx/access.log
maxretry = 2
findtime = 10m
bantime = 24h

[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 5m
bantime = 12h

[nginx-e-mail-abuse]
enabled = true
filter = nginx-e-mail-abuse
port = http,https
logpath = /var/log/nginx/access.log
maxretry = 5
findtime = 10m
bantime = 24h

[recidive]
enabled = true
logpath = /var/log/fail2ban.log
banaction = nftables-e-mail
findtime = 1d
maxretry = 3
bantime = 30d
EOF

    fail2ban-client -d >/dev/null
    systemctl enable --now fail2ban
    systemctl restart fail2ban
}

write_threat_updater() {
    cat > /usr/local/sbin/update-nft-threat-sets.sh <<EOF
#!/bin/sh
set -eu

NFT_BIN="\${NFT_BIN:-/usr/sbin/nft}"
CURL_BIN="\${CURL_BIN:-/usr/bin/curl}"
TABLE_FAMILY="\${TABLE_FAMILY:-inet}"
TABLE_NAME="\${TABLE_NAME:-filter}"
SET_V4="\${SET_V4:-threat_v4}"
SET_V6="\${SET_V6:-threat_v6}"
TIMEOUT="\${TIMEOUT:-$THREAT_SET_TIMEOUT}"
WORKDIR="\$(mktemp -d)"
trap 'rm -rf "\$WORKDIR"' EXIT INT TERM

URLS='https://www.spamhaus.org/drop/drop.txt
https://www.spamhaus.org/drop/edrop.txt
https://rules.emergingthreats.net/fwrules/emerging-Block-IPs.txt
https://iplists.firehol.org/files/firehol_level1.netset
https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt'

fetch_lists() {
    for url in \$URLS; do
        file="\$WORKDIR/\$(basename "\$url")"
        "\$CURL_BIN" --fail --location --silent --show-error --max-time 30 "\$url" -o "\$file" || true
    done
}

extract_ipv4() {
    awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*;/ { next }
        {
            for (i = 1; i <= NF; i++) {
                gsub(/[,;]/, "", \$i)
                if (\$i ~ /^[0-9]{1,3}(\\.[0-9]{1,3}){3}(\\/[0-9]{1,2})?$/) print \$i
            }
        }
    ' "\$WORKDIR"/* | sort -u
}

extract_ipv6() {
    awk '
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*;/ { next }
        {
            for (i = 1; i <= NF; i++) {
                gsub(/[,;]/, "", \$i)
                if (\$i ~ /^[0-9A-Fa-f:]+\\/[0-9]{1,3}$/ && \$i ~ /:/) print \$i
            }
        }
    ' "\$WORKDIR"/* | sort -u
}

write_elements() {
    set_name="\$1"
    input_file="\$2"
    output_file="\$3"

    {
        printf 'flush set %s %s %s\\n' "\$TABLE_FAMILY" "\$TABLE_NAME" "\$set_name"
        while IFS= read -r cidr; do
            [ -n "\$cidr" ] || continue
            printf 'add element %s %s %s { %s timeout %s }\\n' "\$TABLE_FAMILY" "\$TABLE_NAME" "\$set_name" "\$cidr" "\$TIMEOUT"
        done < "\$input_file"
    } > "\$output_file"
}

fetch_lists
extract_ipv4 > "\$WORKDIR/threat_v4.txt"
extract_ipv6 > "\$WORKDIR/threat_v6.txt"

if [ ! -s "\$WORKDIR/threat_v4.txt" ]; then
    echo "No IPv4 threat entries fetched; refusing to flush current nft set" >&2
    exit 1
fi

write_elements "\$SET_V4" "\$WORKDIR/threat_v4.txt" "\$WORKDIR/threat_v4.nft"
write_elements "\$SET_V6" "\$WORKDIR/threat_v6.txt" "\$WORKDIR/threat_v6.nft"

"\$NFT_BIN" -f "\$WORKDIR/threat_v4.nft"
if [ -s "\$WORKDIR/threat_v6.txt" ]; then
    "\$NFT_BIN" -f "\$WORKDIR/threat_v6.nft"
fi

logger -t update-nft-threat-sets "loaded \$(wc -l < "\$WORKDIR/threat_v4.txt") IPv4 and \$(wc -l < "\$WORKDIR/threat_v6.txt") IPv6 entries"
EOF
    chmod 0750 /usr/local/sbin/update-nft-threat-sets.sh

    cat > /etc/cron.d/update-nft-threat-sets <<'EOF'
17 3 * * * root /usr/local/sbin/update-nft-threat-sets.sh
EOF
    chmod 0644 /etc/cron.d/update-nft-threat-sets
}

write_fwknop_config() {
    if [ "$ENABLE_FWKNOP" != "1" ]; then
        return
    fi
    local fwknop_key fwknop_hmac client_file

    backup_file /etc/fwknop/access.conf
    install -d -m 0750 /etc/fwknop
    client_file="/root/fwknop-client-${MAIL_HOSTNAME}.conf"

    if [ -s /etc/fwknop/access.conf ] && ! grep -q 'CHANGE_ME' /etc/fwknop/access.conf; then
        log "existing /etc/fwknop/access.conf has real keys; keeping it"
    else
        fwknop_key="$(openssl rand -base64 32)"
        fwknop_hmac="$(openssl rand -base64 32)"
        cat > /etc/fwknop/access.conf <<EOF
SOURCE                  ANY;
REQUIRE_SOURCE_ADDRESS  Y;
OPEN_PORTS              tcp/$SSH_PORT;
KEY_BASE64              $fwknop_key;
HMAC_KEY_BASE64         $fwknop_hmac;
HMAC_DIGEST_TYPE        SHA256;
FW_ACCESS_TIMEOUT       60;
CMD_CYCLE_OPEN          nft add element inet filter fwknop_ssh_v4 { \$SRC timeout 60s };
CMD_CYCLE_CLOSE         nft delete element inet filter fwknop_ssh_v4 { \$SRC };
CMD_CYCLE_TIMER         60;
ENABLE_CMD_EXEC         Y;
EOF
        chmod 0600 /etc/fwknop/access.conf

        cat > "$client_file" <<EOF
# Copy this stanza to the admin workstation fwknop rc file, then remove it from the VPS if desired.
[${MAIL_HOSTNAME}-ssh]
ACCESS                      tcp/$SSH_PORT
SPA_SERVER                  $MAIL_HOSTNAME
SPA_SERVER_PORT             $FWKNOP_PORT
KEY_BASE64                  $fwknop_key
HMAC_KEY_BASE64             $fwknop_hmac
HMAC_DIGEST_TYPE            SHA256
USE_HMAC                    Y
EOF
        chmod 0600 "$client_file"
    fi

    if [ -e /etc/fwknop/fwknopd.conf ]; then
        backup_file /etc/fwknop/fwknopd.conf
        if grep -q '^PCAP_INTF' /etc/fwknop/fwknopd.conf; then
            sed -i "s/^PCAP_INTF.*/PCAP_INTF                   $WAN_IF;/" /etc/fwknop/fwknopd.conf
        else
            printf '\nPCAP_INTF                   %s;\n' "$WAN_IF" >> /etc/fwknop/fwknopd.conf
        fi
    fi

    touch /var/log/fwknopd.log
    systemctl enable fwknop-server
    systemctl restart fwknop-server
    log "fwknop server configured; client stanza saved to $client_file"
}

write_wireguard_placeholder() {
    if [ "$ENABLE_WIREGUARD_PLACEHOLDER" != "1" ]; then
        return
    fi
    install -d -m 0700 /etc/wireguard
    if [ ! -e /etc/wireguard/README.bootstrap ]; then
        cat > /etc/wireguard/README.bootstrap <<EOF
WireGuard tools are installed. Create /etc/wireguard/$WG_IF.conf with your private key and peers, then run:

systemctl enable --now wg-quick@$WG_IF

The nftables rules already allow UDP/$WG_PORT and admin access from interface $WG_IF.
EOF
        chmod 0600 /etc/wireguard/README.bootstrap
    fi
}

final_checks() {
    sshd -t
    nft -c -f /etc/nftables.conf
    /usr/local/sbin/fail2ban-nft-e-mail.sh check
    fail2ban-client status >/dev/null
}

main() {
    require_root
    detect_wan_if
    detect_admin_cidr
    validate_admin_cidr

    log "WAN_IF=$WAN_IF WG_IF=$WG_IF ADMIN_CIDR=$ADMIN_CIDR SSH_PORT=$SSH_PORT INSTALL_USER=$INSTALL_USER"
    ensure_apt
    prepare_log_files
    write_postfix_abuse_controls
    install_ssh_key
    write_nftables
    write_fail2ban_helper
    write_fail2ban
    write_threat_updater
    write_fwknop_config
    write_wireguard_placeholder
    harden_sshd
    final_checks

    log "done. Open a second SSH session using a key before closing the current one."
    log "threat feeds can be loaded manually with: /usr/local/sbin/update-nft-threat-sets.sh"
}

main "$@"
