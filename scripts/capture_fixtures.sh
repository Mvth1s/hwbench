#!/usr/bin/env bash
# Capture les sorties réelles de cette machine pour tests/fixtures/<nom>/, anonymisées.
#
# Usage : scripts/capture_fixtures.sh [nom]
#   À lancer SANS sudo : glxinfo/vulkaninfo ont besoin de la session graphique.
#   Le script demande sudo lui-même pour dmidecode, smartctl et la lecture des serials DMI.
#   <nom> par défaut : fabricant + modèle (ex. dell-inc-latitude-5420), jamais le hostname.
#
# Rien n'est modifié sur le système. Les sorties brutes restent dans un dossier temporaire
# (mode 700) supprimé à la fin ; seules les versions anonymisées sont écrites dans le repo.
set -euo pipefail
export LC_ALL=C

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -eq 0 ]]; then
    echo "Relance sans sudo : glxinfo et vulkaninfo ont besoin de ta session graphique." >&2
    echo "Le script demandera sudo lui-même pour dmidecode et smartctl." >&2
    exit 1
fi

RAW="$(mktemp -d)"
chmod 700 "$RAW"
trap 'rm -rf "$RAW"' EXIT

have() { command -v "$1" >/dev/null 2>&1; }

# capture <fichier> <commande...> ; les codes retour non nuls sont tolérés
# (smartctl renvoie un masque de bits même quand la sortie est valide)
capture() {
    local out="$1"; shift
    local tool="$1"
    [[ "$tool" == sudo ]] && tool="$2"
    if have "$tool"; then
        "$@" >"$RAW/$out" 2>/dev/null || true
        [[ -s "$RAW/$out" ]] || rm -f "$RAW/$out"
        echo "  ok  $out"
    else
        echo "  --  $out (absent : $tool)"
    fi
}

echo "Sorties utilisateur :"
capture lscpu.json lscpu -J
capture lsblk.json lsblk -J -b -o NAME,SIZE,MODEL,TYPE,ROTA,TRAN
capture lspci_mm.txt lspci -mm -nn
capture glxinfo_B.txt glxinfo -B
capture vulkaninfo_summary.txt vulkaninfo --summary
capture nvidia_smi.csv nvidia-smi --query-gpu=name,driver_version,memory.total \
    --format=csv,noheader,nounits
capture smartctl_version.txt smartctl --version

echo "Sorties root (sudo) :"
if sudo -v; then
    capture dmidecode_memory.txt sudo dmidecode -t memory
    for disk in $(lsblk -dn -o NAME,TYPE | awk '$2 == "disk" { print $1 }' \
                  | grep -Ev '^(zram|loop|ram)' || true); do
        capture "smartctl_${disk}.json" sudo smartctl -j -a "/dev/${disk}"
    done
    # Valeurs réelles lues uniquement pour vérifier qu'elles n'apparaissent nulle part.
    for f in product_uuid product_serial board_serial chassis_serial; do
        sudo cat "/sys/class/dmi/id/$f" 2>/dev/null >>"$RAW/.secrets" || true
    done
else
    echo "  sudo indisponible : dmidecode et smartctl ne sont pas capturés." >&2
fi

PYTHON="$REPO/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3

PYTHONPATH="$REPO/src" "$PYTHON" - "$RAW" "$REPO/tests/fixtures" "${1:-}" <<'PY'
import json
import re
import shutil
import socket
import sys
from pathlib import Path

from hwbench.privacy import SENSITIVE_KEY_RE

raw, fixtures_root, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
MAC_RE = re.compile(r"\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b", re.I)
LONG_HEX_RE = re.compile(r"\b(?:eui\.|naa\.|0x)?[0-9a-f]{16}(?:[0-9a-f]{16})?\b", re.I)
EMPTY = {"", "not specified", "unknown", "none", "not provided", "default string",
         "to be filled by o.e.m.", "no asset tag", "not available"}
TEXT_ID_LINE_RE = re.compile(r"^(\s*(?:serial number|asset tag|uuid|serial)\s*:\s*)(.*?)\s*$",
                             re.I | re.M)


def read(path: str) -> str | None:
    try:
        return Path(path).read_text(errors="replace").strip()
    except OSError:
        return None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# --- secrets connus de cette machine : servent au remplacement littéral et à la vérification
secrets = {socket.gethostname()}
secrets |= {line.strip() for line in (read(raw / ".secrets") or "").splitlines()}
for addr in Path("/sys/class/net").glob("*/address"):
    secrets.add(read(addr) or "")
for f in ("board_asset_tag", "chassis_asset_tag"):
    secrets.add(read(f"/sys/class/dmi/id/{f}") or "")
secrets = {s for s in secrets if len(s) >= 4 and s.lower() not in EMPTY
           and s not in {"00:00:00:00:00:00", "localhost", ZERO_UUID}}

counter = iter(range(1, 10_000))


def secret_re(secret: str) -> re.Pattern[str]:
    # bornes de mot : un hostname « dell » ne doit pas casser « dell_smm »
    return re.compile(rf"(?<![\w-]){re.escape(secret)}(?![\w-])", re.I)


def fake(prefix: str = "FAKE") -> str:
    return f"{prefix}-{next(counter):04d}"


def scrub_text(text: str) -> str:
    text = TEXT_ID_LINE_RE.sub(
        lambda m: m.group(0) if m.group(2).lower() in EMPTY else m.group(1) + fake(), text
    )
    text = UUID_RE.sub(ZERO_UUID, text)
    text = MAC_RE.sub("FAKE-MAC", text)
    for secret in secrets:
        text = secret_re(secret).sub("FAKE-SECRET", text)
    return text


def scrub_json(obj, sensitive: bool = False):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key_sensitive = sensitive or bool(SENSITIVE_KEY_RE.search(str(k)))
            if key_sensitive and isinstance(v, dict):
                # wwn / eui64 : naa/oui = type et fabricant, id/ext_id = l'unité
                out[k] = {sk: (0 if sk in ("id", "ext_id") else sv) for sk, sv in v.items()}
            else:
                out[k] = scrub_json(v, key_sensitive)
        return out
    if isinstance(obj, list):
        return [scrub_json(v, sensitive) for v in obj]
    if isinstance(obj, str):
        if sensitive and obj.strip().lower() not in EMPTY:
            return ZERO_UUID if UUID_RE.fullmatch(obj) else fake()
        return LONG_HEX_RE.sub("FAKE-HEX", scrub_text(obj))
    if sensitive and isinstance(obj, int) and not isinstance(obj, bool):
        return 0
    return obj


def capture_sysfs() -> dict[str, str]:
    files: dict[str, str] = {}

    def add(path: Path | str, value: str | None = None) -> None:
        value = read(path) if value is None else value
        if value is not None:
            files[str(path)] = value

    add("/proc/meminfo")
    add("/proc/sys/kernel/hostname", "fake-host")
    dmi = Path("/sys/class/dmi/id")
    for f in ("sys_vendor", "product_name", "product_version", "board_vendor", "board_name",
              "bios_vendor", "bios_version", "bios_date"):
        add(dmi / f)
    add(dmi / "product_uuid", ZERO_UUID)
    for f, value in (("product_serial", "FAKE-SYS-SERIAL"), ("board_serial", "FAKE-BOARD-SERIAL"),
                     ("chassis_serial", "FAKE-CHASSIS-SERIAL")):
        add(dmi / f, value)
    for f in ("board_asset_tag", "chassis_asset_tag"):
        real = read(dmi / f)
        if real is not None:
            add(dmi / f, real if real.lower() in EMPTY else "FAKE-ASSET-TAG")
    for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*")):
        for f in ("scaling_cur_freq", "scaling_governor", "scaling_driver",
                  "energy_performance_preference", "boost"):
            add(cpu / "cpufreq" / f)
    # mode des pilotes amd-pstate / intel_pstate (active, passive, guided), boost global
    add("/sys/devices/system/cpu/amd_pstate/status")
    add("/sys/devices/system/cpu/intel_pstate/status")
    add("/sys/devices/system/cpu/cpufreq/boost")
    add("/sys/firmware/acpi/platform_profile")
    add("/sys/firmware/acpi/platform_profile_choices")
    for ps in sorted(Path("/sys/class/power_supply").iterdir() if Path("/sys/class/power_supply").exists() else []):
        for f in ("type", "scope", "online", "capacity", "status", "energy_full",
                  "energy_full_design", "charge_full", "charge_full_design",
                  "voltage_min_design", "cycle_count"):
            add(ps / f)
    for hw in sorted(Path("/sys/class/hwmon").iterdir() if Path("/sys/class/hwmon").exists() else []):
        add(hw / "name")
        for f in sorted(hw.iterdir()):
            if re.fullmatch(r"(temp\d+_(input|label|max|crit)|fan\d+_(input|label))", f.name):
                add(f)
    return files


# --- nom du dossier : fabricant + modèle, jamais le hostname
if not name:
    vendor = read("/sys/class/dmi/id/sys_vendor") or ""
    product = read("/sys/class/dmi/id/product_name") or ""
    name = slug(f"{vendor} {product}") or "machine"
name = slug(name)

outputs: dict[str, str] = {}
for path in sorted(raw.iterdir()):
    if path.name.startswith("."):
        continue
    text = path.read_text(errors="replace")
    if path.suffix == ".json":
        try:
            outputs[path.name] = json.dumps(scrub_json(json.loads(text)), indent=2) + "\n"
        except json.JSONDecodeError:
            print(f"  !! {path.name} : JSON invalide, ignoré", file=sys.stderr)
    else:
        outputs[path.name] = scrub_text(text)
outputs["sysfs.json"] = json.dumps(
    {k: scrub_text(v) if "hostname" not in k else v for k, v in capture_sysfs().items()},
    indent=2, ensure_ascii=False,
) + "\n"

# --- vérification finale : rien n'est écrit si un identifiant réel subsiste
leaks = []
for fname, content in outputs.items():
    leaks += [f"{fname}: identifiant connu" for s in secrets if secret_re(s).search(content)]
    leaks += [f"{fname}: UUID {u}" for u in UUID_RE.findall(content) if u != ZERO_UUID]
    leaks += [f"{fname}: MAC" for _ in MAC_RE.findall(content)]
if leaks:
    print("Abandon, anonymisation incomplète :", *sorted(set(leaks)), sep="\n  ", file=sys.stderr)
    sys.exit(1)

dest = fixtures_root / name
if dest.exists():
    shutil.rmtree(dest)
dest.mkdir(parents=True)
for fname, content in outputs.items():
    (dest / fname).write_text(content)
print(f"\nFixtures écrites dans {dest.relative_to(fixtures_root.parent.parent)}/ :")
for fname in sorted(outputs):
    print(f"  {fname}")
PY

if [[ -x "$REPO/.venv/bin/pytest" ]]; then
    echo
    "$REPO/.venv/bin/pytest" -q "$REPO/tests/test_fixtures_privacy.py" "$REPO/tests/test_real_fixtures.py"
fi
