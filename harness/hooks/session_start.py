"""SessionStart hook: proves the dispatcher's hooks fire in this session."""
import hookcommon as hc

data = hc.read_input()
hc.write_marker(hc.env(), "hooks_loaded", source=data.get("source"), claude_session=data.get("session_id"))
