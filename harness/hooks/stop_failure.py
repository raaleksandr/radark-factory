"""StopFailure hook: record a usage-limit failure (or any other API failure) for the dispatcher."""
import json

import hookcommon as hc

data = hc.read_input()
text = json.dumps(data).lower()
event = "usage_limit" if ("rate_limit" in text or "usage limit" in text) else "error"
hc.write_marker(hc.env(), event, detail={k: v for k, v in data.items() if k != "transcript_path"})
