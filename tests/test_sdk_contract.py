"""Kunci seam SDK native <-> backend.

`sdk/contract/` berisi fixture yang DIHASILKAN dari kode yang sedang
berjalan, bukan diketik tangan. Berkas ini memastikan fixture itu tidak
pernah basi diam-diam: ia membangun ulang seluruhnya di memori, lalu
membandingkannya dengan yang tersimpan di repo.

Alasannya sama persis dengan test_frontend.py. Penulis SDK ada di mesin
lain dan tidak akan tahu kalau bentuk tanggapan bergeser; yang ia punya
hanya fixture di repo ini. Fixture yang basi lebih berbahaya daripada
tidak ada fixture — ia terlihat otoritatif.

Kalau berkas ini merah, kontraknya bergeser. Tanyakan dulu: disengaja?
  ya    jalankan `python scripts/sdk_contract.py generate`,
        lalu BERI TAHU penulis SDK-nya — itu bagian yang tidak bisa
        diotomatiskan
  tidak batalkan perubahannya

    python tests/test_sdk_contract.py
"""

import json
import os
import sys

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Berdiri sendiri: tidak menuntut PYTHONPATH disetel dari luar, supaya
# preflight dan siapa pun bisa menjalankannya langsung.
sys.path.insert(0, os.path.join(AKAR, "scripts"))

import sdk_contract  # noqa: E402

KONTRAK = os.path.join(AKAR, "sdk", "contract")
_hasil = []


def cek(nama):
    def deco(fn):
        try:
            _hasil.append((nama, True, fn() or ""))
        except AssertionError as exc:
            _hasil.append((nama, False, str(exc)))
        return fn
    return deco


def _tersimpan(nama):
    with open(os.path.join(KONTRAK, f"{nama}.json"), encoding="utf-8") as f:
        return json.load(f)


@cek("Fixture di repo sama persis dengan keluaran kode hari ini")
def _s1():
    assert os.path.isdir(KONTRAK), (
        "sdk/contract/ tidak ada — jalankan "
        "python scripts/sdk_contract.py generate")
    hidup = sdk_contract.bangun()

    ada = {f[:-5] for f in os.listdir(KONTRAK)
           if f.endswith(".json") and not f.startswith("skema-")}
    assert ada == set(hidup), (
        f"daftar fixture bergeser — hanya di repo: {sorted(ada - set(hidup))}, "
        f"hanya di kode: {sorted(set(hidup) - ada)}")

    beda = []
    for nama, isi in hidup.items():
        lama = _tersimpan(nama)
        for bagian in ("status_http", "permintaan", "tanggapan"):
            if lama.get(bagian) != isi[bagian]:
                beda.append(f"{nama}.{bagian}")
    assert not beda, (
        "fixture basi: " + ", ".join(beda) +
        " — jalankan scripts/sdk_contract.py generate DAN beri tahu "
        "penulis SDK")
    return f"{len(hidup)} fixture cocok byte per byte"


@cek("Tiap tier aksi dan tiap status integritas punya fixture-nya")
def _s2():
    hidup = sdk_contract.bangun()
    aksi = {d["tanggapan"]["action"] for d in hidup.values()}
    integritas = {d["tanggapan"]["device_integrity"] for d in hidup.values()}

    # Penulis SDK harus bisa merender SETIAP keadaan tanpa menebak.
    kurang_aksi = {"proceed", "warn", "step_up", "cooling_off"} - aksi
    assert not kurang_aksi, f"tier tanpa fixture: {sorted(kurang_aksi)}"
    kurang_int = {"not_provided", "reported", "attested", "failed"} - integritas
    assert not kurang_int, f"status integritas tanpa fixture: {sorted(kurang_int)}"
    return f"{len(aksi)} tier, {len(integritas)} status integritas terwakili"


@cek("Tanggapan dan jejak audit tidak pernah berbeda soal integritas")
def _s3():
    # Bug nyata yang pernah ada: cabang mock location lupa meneruskan
    # status integritas ke audit, jadi peristiwa paling serius tercatat
    # sebagai "not_provided". Fixture inilah yang memunculkannya.
    hidup = sdk_contract.bangun()
    mock = hidup["06-android-mock-location"]["tanggapan"]
    assert mock["device_integrity"] == "failed", (
        f"mock location -> {mock['device_integrity']}, harusnya failed")
    assert mock["action"] == "step_up", (
        f"mock location -> {mock['action']}, harusnya step_up")
    assert "mock_location_reported" in mock["signals"]
    return "mock location: failed + step_up + sinyal eksplisit"


@cek("Skema OpenAPI yang dipakai SDK ikut tersimpan")
def _s4():
    with open(os.path.join(KONTRAK, "skema-openapi.json"), encoding="utf-8") as f:
        skema = json.load(f)
    for n in ("VerifyRequest", "DeviceIntegrity", "VerifyResponse"):
        assert n in skema, f"skema {n} hilang dari sdk/contract/"

    wajib = set(skema["VerifyRequest"].get("required", []))
    # accuracy_m pernah opsional dan dijadikan wajib — perubahan yang
    # benar, tapi ia MEMATAHKAN klien. Penulis SDK harus melihatnya.
    assert "accuracy_m" in wajib, "accuracy_m tidak lagi wajib di skema SDK"
    for f_ in ("payload", "lat", "lng", "device_anon_id"):
        assert f_ in wajib, f"{f_} hilang dari daftar wajib"
    assert "device_integrity" not in wajib, (
        "device_integrity jadi WAJIB — itu mengunci seluruh klien web keluar")
    return f"{len(wajib)} field wajib; device_integrity tetap opsional"


print("=" * 70)
print("SEAM SDK <-> BACKEND")
print("=" * 70)
print()
gagal = 0
for nama, ok, detail in _hasil:
    print(f"  [{'OK   ' if ok else 'GAGAL'}]  {nama}")
    if detail:
        print(f"           {detail}")
    if not ok:
        gagal += 1
print()
print("-" * 70)
if gagal:
    print(f"{gagal} dari {len(_hasil)} pemeriksaan GAGAL.")
    sys.exit(1)
print(f"Seluruh {len(_hasil)} pemeriksaan lolos.")
