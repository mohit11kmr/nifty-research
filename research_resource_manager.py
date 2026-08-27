"""Phase I.3 - Research Resource Manager (spec section 6).

Reads the physical machine profile ONCE, derives safe execution defaults
(worker count, memory ceilings, disk archive mode), and writes a frozen
resource profile into results/phase_i3/resource_profile.json. All Phase I.3
parallelism and memory decisions derive from this single source of truth so
the run is reproducible on the audited machine.

Safety defaults:
  * workers = max(1, physical_cores - 1)          (never saturate the box)
  * ram_target_pct  = 0.60 of available RAM        (keep the OS breathing)
  * archive_mode    = True when free disk < 15%    (avoid filling the disk)
"""
import json
import os
import shutil

REPO = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(REPO, "results", "phase_i3")
PROFILE_PATH = os.path.join(RESULTS_DIR, "resource_profile.json")

DISK_FREE_MIN_PCT = 15.0
RAM_TARGET_PCT = 0.60
WORKERS_HEADROOM = 1


def _meminfo():
    """Linux /proc/meminfo -> (total_mb, available_mb). Fallback to shutil."""
    try:
        with open("/proc/meminfo") as fh:
            fields = {}
            for line in fh:
                key, rest = line.split(":", 1)
                fields[key.strip()] = int(rest.split()[0])  # kB
        total_kb = fields.get("MemTotal")
        avail_kb = fields.get("MemAvailable") or fields.get("MemFree")
        return total_kb // 1024, avail_kb // 1024
    except Exception:
        du = shutil.disk_usage(REPO)
        return du.total // (1024 ** 2), du.free // (1024 ** 2)


def _disk_free_pct():
    du = shutil.disk_usage(REPO)
    return 100.0 * du.free / du.total


def _physical_cores():
    try:
        import os as _os
        return _os.cpu_count() or 1
    except Exception:
        return 1


def detect_profile():
    total_mb, avail_mb = _meminfo()
    cores = _physical_cores()
    free_pct = _disk_free_pct()
    workers = max(1, cores - WORKERS_HEADROOM)
    ram_target_mb = int(avail_mb * RAM_TARGET_PCT)
    return {
        "physical_cores": cores,
        "workers": workers,
        "ram_total_mb": total_mb,
        "ram_available_mb": avail_mb,
        "ram_target_mb": ram_target_mb,
        "ram_target_pct": RAM_TARGET_PCT,
        "disk_free_pct": round(free_pct, 2),
        "disk_free_min_pct": DISK_FREE_MIN_PCT,
        "archive_mode": free_pct < DISK_FREE_MIN_PCT,
        "safe_defaults": {
            "workers": workers,
            "ram_target_mb": ram_target_mb,
            "archive_only": free_pct < DISK_FREE_MIN_PCT,
        },
    }


def load_profile(refresh=False):
    """Frozen profile on disk; refresh=True re-detects and re-writes."""
    if refresh or not os.path.exists(PROFILE_PATH):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        profile = detect_profile()
        with open(PROFILE_PATH, "w") as fh:
            json.dump(profile, fh, indent=2, sort_keys=True)
        return profile
    with open(PROFILE_PATH) as fh:
        return json.load(fh)


if __name__ == "__main__":
    print(json.dumps(load_profile(refresh=True), indent=2))
