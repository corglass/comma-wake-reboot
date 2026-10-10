"""Same path as Settings > Device > Power Off:
openpilot/selfdrive/ui/layouts/settings/device.py -> params.put_bool("DoShutdown", True)
openpilot/system/manager/manager.py sees DoShutdown, stops processes cleanly, calls HARDWARE.shutdown()."""
import subprocess

def do_shutdown(log, dry_run=False):
    if dry_run:
        log("DRY RUN: would set Params DoShutdown=True"); return True
    try:
        try:
            from openpilot.common.params import Params
        except ImportError:
            from common.params import Params
        Params().put_bool("DoShutdown", True)
        log("Params DoShutdown=True written; manager will power off cleanly")
        return True
    except Exception as e:
        log(f"Params write failed: {e}. NOT forcing power off automatically.")
        log("Manual fallback (documented): sudo systemctl poweroff")
        return False
