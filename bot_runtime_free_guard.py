from pathlib import Path

# Free-plan traffic guard.
# Keep the existing bot/runtime logic intact and only reduce background
# Supabase traffic. Direct order/status/stock writes remain event-driven.
# Delta reconciliation runs every 5 minutes; full reconciliation remains
# as a safety net every 6 hours.
source = Path("bot_runtime_launcher.py").read_text(encoding="utf-8")

old_full = "full_reconcile_every = 60 * 60"
new_full = "full_reconcile_every = 6 * 60 * 60"
old_delta = "time.sleep(SYNC_INTERVAL)"
new_delta = "time.sleep(5 * 60)"

if old_full not in source:
    raise RuntimeError(
        "Free-plan guard could not find the expected reconcile setting; "
        "refusing to start with an unknown runtime instead of changing behavior blindly."
    )
if old_delta not in source:
    raise RuntimeError(
        "Free-plan guard could not find the expected delta-sync interval; "
        "refusing to start with an unknown runtime instead of changing behavior blindly."
    )

source = source.replace(old_full, new_full, 1)
source = source.replace(old_delta, new_delta, 1)
namespace = {"__name__": "__main__", "__file__": "bot_runtime_launcher.py"}
exec(compile(source, "bot_runtime_launcher.py", "exec"), namespace, namespace)
