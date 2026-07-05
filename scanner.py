#!/usr/bin/env python3
"""
Проверка IP-адресов Yandex Cloud CDN для api-1.catgroupmeow.xyz
Путь: /api/v1/assets/
Успех = HTTP 400.
Источник IP: https://tech.cdn.yandex.net/prefixes/yc.json
"""

import ipaddress
import json
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_DOMAIN = "api-1.catgroupmeow.xyz"
TARGET_PATH = "/api/v1/assets/"
CDN_PREFIXES_URL = "https://tech.cdn.yandex.net/prefixes/yc.json"
THREADS = 20
TIMEOUT = 10


def fetch_prefixes():
    import urllib.request
    try:
        with urllib.request.urlopen(CDN_PREFIXES_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("prefixes", [])
    except Exception as e:
        print(f"[!] Не удалось загрузить {CDN_PREFIXES_URL}: {e}")
        return []


def expand_cidr(cidr):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return [str(ip) for ip in network.hosts()]
    except ValueError:
        return []


def check_ip(ip):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((ip, 443))

        # Создаём контекст с поддержкой renegotiation
        context = ssl.create_default_context()
        # Отключаем проверку сертификата (если нужно, можно включить)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        # Включаем renegotiation (доступно в Python 3.10+)
        if hasattr(ssl, 'OP_ENABLE_RENEGOTIATION'):
            context.options |= ssl.OP_ENABLE_RENEGOTIATION

        tls_sock = context.wrap_socket(sock, server_hostname=TARGET_DOMAIN)

        request = (
            f"GET {TARGET_PATH} HTTP/1.1\r\n"
            f"Host: {TARGET_DOMAIN}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        tls_sock.send(request.encode())

        # Читаем ответ, пока не получим пустую строку (заголовки)
        response = b""
        while True:
            chunk = tls_sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\r\n\r\n" in response:
                break

        tls_sock.close()

        if response:
            status_line = response.split(b"\r\n")[0].decode("utf-8", errors="ignore")
            if status_line.startswith("HTTP/") and " " in status_line:
                code = int(status_line.split(" ")[1])
                return ip, code == 400, code

        return ip, False, None

    except Exception:
        return ip, False, None


def main():
    print("[*] Загрузка префиксов из Yandex Cloud CDN...")
    prefixes = fetch_prefixes()
    if not prefixes:
        print("[!] Не удалось получить префиксы.")
        return

    print(f"[*] Получено {len(prefixes)} префиксов. Разворачиваем...")
    all_ips = []
    for cidr in prefixes:
        ips = expand_cidr(cidr)
        all_ips.extend(ips)
        print(f"    {cidr} -> {len(ips)} адресов")

    if not all_ips:
        print("[!] Нет IP-адресов.")
        return

    print(f"\n[*] Всего IP: {len(all_ips)}")
    print(f"[*] Ищем IP с ответом 400 на {TARGET_PATH}...\n")

    working_ips = []
    total = len(all_ips)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(check_ip, ip): ip for ip in all_ips}
        for idx, future in enumerate(as_completed(futures), start=1):
            ip, is_ok, code = future.result()
            if is_ok:
                working_ips.append(ip)
                status = "✅"
            else:
                status = "❌"
            code_str = f" (HTTP {code})" if code is not None else " (ошибка)"
            print(f"[{idx}/{total}] {ip} {status}{code_str}")

    print("\n" + "=" * 60)
    if working_ips:
        print(f"✅ Найдено {len(working_ips)} IP, отвечающих 400:")
        for ip in working_ips:
            print(f"  - {ip}")
        print("\nПример curl:")
        example = working_ips[0]
        print(f'  curl --resolve {TARGET_DOMAIN}:443:{example} https://{TARGET_DOMAIN}{TARGET_PATH}')
    else:
        print(f"❌ Не найдено ни одного IP с кодом 400 на {TARGET_PATH}.")


if __name__ == "__main__":
    main()
