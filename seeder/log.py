"""One JSON object for each line on standard output, so a log shipper can read it"""

import json
import sys
import time


def log(event, **fields):
    print(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}), file=sys.stdout, flush=True)
