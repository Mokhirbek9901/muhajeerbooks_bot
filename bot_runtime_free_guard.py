from pathlib import Path

# Free-plan traffic guard.
# Keep the existing bot/runtime logic intact and only reduce expensive full
# Supabase reconciliations. Delta sync remains unchanged, so new/changed
# books and orders continue syncing on the normal interval.
source = Path("bot_runtime_launcher.py").read_text(encoding="utf-8")

old = "full_reconcile_every = 60 * 60"
new = "full_reconcile_every = 6 * 60 * 60"

if old not in source:
    raise RuntimeError(
        "Free-plan guard could not find the expected reconcile setting; "
        "refusing to start with an unknown runtime instead of changing behavior blindly."
    )

source = source.replace(old, new, 1)
namespace = {"__name__": "__main__", "__file__": "bot_runtime_launcher.py"}
exec(compile(source, "bot_runtime_launcher.py", "exec"), namespace, namespace)
