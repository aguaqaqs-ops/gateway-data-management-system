"""Do not restart the A stack after an incomplete reset."""
from reset_manager import status

if status()['state'] != 'success':
    raise SystemExit('single-device reset is not complete')
