"""
Sertifikat HTTPS lokal supaya demo bisa dijalankan dari HP.

Kenapa ini wajib, bukan pilihan. Browser menuntut *secure context*
untuk dua hal yang justru menjadi inti demo Q-Shield:

    navigator.mediaDevices.getUserMedia   kamera, untuk memindai QR
    navigator.geolocation                 lokasi, untuk jangkar

Membuka `http://192.168.x.x:8000` dari HP BUKAN secure context, jadi
browser memblokir keduanya tanpa bisa dinegosiasikan. `localhost`
dikecualikan — tapi HP tidak bisa membuka localhost laptop.

Jadi tanpa HTTPS, frontend secantik apa pun tidak bisa memindai
maupun tahu lokasi, dan demo mati sebelum dimulai.

    python scripts/make_cert.py                 deteksi IP LAN otomatis
    python scripts/make_cert.py 192.168.1.5     tentukan sendiri

Menghasilkan certs/cert.pem dan certs/key.pem, lalu mencetak perintah
menjalankan servernya.

Sertifikatnya self-signed, jadi HP akan menampilkan peringatan sekali.
Terima peringatan itu SEBELUM hari-H, bukan di depan juri — setelah
diterima, browser mengingatnya.
"""

import ipaddress
import os
import socket
import subprocess
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(AKAR, "certs")
HARI_BERLAKU = 365


def ip_lan() -> str:
    """Alamat LAN mesin ini, dilihat dari sisi jaringan.

    Soket UDP dibuka ke alamat luar tanpa benar-benar mengirim apa pun;
    yang diambil adalah alamat lokal yang dipilih kernel untuk rute itu.
    Cara ini menemukan antarmuka yang sungguh dipakai, bukan yang
    kebetulan pertama terdaftar.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def subnet_lokal(alamat: str):
    """Rentang jaringan tempat alamat ini berada, dibaca dari netmask.

    DHCP di jaringan kampus memindahkan alamat laptop berkali-kali
    sehari — di proyek ini tujuh kali dalam seminggu. Sertifikat yang
    hanya sah untuk satu alamat berarti APK harus dibangun ulang tiap
    kali itu terjadi, karena sertifikatnya ikut dibundel di dalamnya.

    Menerbitkannya untuk seluruh rentang menghapus pembangunan ulang
    itu; yang tersisa hanya mengganti satu isian alamat di aplikasi.
    """
    hasil = subprocess.run(["ifconfig"], capture_output=True, text=True)
    for baris in hasil.stdout.split("\n"):
        if f"inet {alamat} " in baris and "netmask" in baris:
            mask = baris.split("netmask")[1].split()[0]
            bits = bin(int(mask, 16)).count("1") if mask.startswith("0x") else None
            if bits:
                return ipaddress.ip_network(f"{alamat}/{bits}", strict=False)
    return None


def buat(alamat: str, seluruh_subnet: bool = False) -> int:
    try:
        ipaddress.ip_address(alamat)
    except ValueError:
        print(f"'{alamat}' bukan alamat IP yang sah", file=sys.stderr)
        return 2

    os.makedirs(FOLDER, exist_ok=True)
    cert = os.path.join(FOLDER, "cert.pem")
    key = os.path.join(FOLDER, "key.pem")

    # SAN wajib memuat alamat IP-nya. Browser modern mengabaikan
    # Common Name sepenuhnya dan hanya melihat Subject Alternative Name;
    # sertifikat tanpa SAN akan ditolak walau CN-nya benar.
    entri = [f"IP:{alamat}", "IP:127.0.0.1", "DNS:localhost"]
    cakupan = alamat

    net = subnet_lokal(alamat) if seluruh_subnet else None
    if net and net.num_addresses <= 4096:
        # X.509 tidak mengenal notasi CIDR untuk iPAddress — tiap alamat
        # harus disebut satu per satu.
        entri = [f"IP:{ip}" for ip in net.hosts()]
        entri += ["IP:127.0.0.1", "DNS:localhost"]
        cakupan = f"{net} ({net.num_addresses - 2} alamat)"
    elif seluruh_subnet:
        print("  rentang jaringan tidak terbaca atau terlalu besar — "
              "pakai satu alamat saja", file=sys.stderr)

    san = ",".join(entri)

    # Daftar sepanjang ini tidak muat dilewatkan sebagai argumen baris
    # perintah, jadi ditulis ke berkas konfigurasi sementara.
    konf = os.path.join(FOLDER, ".san.cnf")
    with open(konf, "w") as f:
        f.write("[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n"
                "[dn]\nC=ID\nO=Q-Shield Demo\nCN=qshield.local\n"
                "[v3]\nbasicConstraints=critical,CA:TRUE\n"
                f"subjectAltName={san}\n")

    perintah = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key, "-out", cert,
        "-days", str(HARI_BERLAKU), "-nodes",
        "-config", konf,
    ]
    hasil = subprocess.run(perintah, capture_output=True, text=True)
    os.remove(konf)
    if hasil.returncode != 0:
        print("openssl gagal:", file=sys.stderr)
        print(hasil.stderr, file=sys.stderr)
        return 1
    san = f"{cakupan} + 127.0.0.1 + localhost"

    os.chmod(key, 0o600)

    print("=" * 68)
    print("Sertifikat HTTPS lokal siap")
    print("=" * 68)
    print()
    print(f"  cert : {cert}")
    print(f"  key  : {key}  (mode 600)")
    print(f"  SAN  : {san}")
    print(f"  masa : {HARI_BERLAKU} hari")
    print()
    print("Jalankan servernya:")
    print()
    print(f"  uvicorn qshield.api:app --host 0.0.0.0 --port 8000 \\")
    print(f"      --ssl-certfile {os.path.relpath(cert, AKAR)} \\")
    print(f"      --ssl-keyfile {os.path.relpath(key, AKAR)}")
    print()
    print("Buka dari HP (satu WiFi dengan laptop):")
    print()
    print(f"  https://{alamat}:8000/")
    print()
    print("HP akan memperingatkan sertifikatnya tidak dikenal. Itu wajar")
    print("untuk self-signed. Terima peringatannya SEKARANG, jangan di")
    print("depan juri — setelah diterima, browser mengingatnya.")
    print()
    print("Kalau IP laptop berubah (pindah WiFi), jalankan ulang skrip ini.")
    return 0


if __name__ == "__main__":
    arg = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Bawaannya mencakup seluruh rentang jaringan; pakai --satu-alamat
    # kalau memang hanya satu yang diinginkan.
    sys.exit(buat(arg[0] if arg else ip_lan(),
                  seluruh_subnet="--satu-alamat" not in sys.argv))
