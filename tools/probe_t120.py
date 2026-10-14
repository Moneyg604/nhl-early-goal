"""Probe: can the runner read the NHL schedule the way the keeper does, and what T-120 does it compute?"""
import sys, importlib.util
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("k", "tools/keeper.py"); k = importlib.util.module_from_spec(spec); spec.loader.exec_module(k)
now = datetime.now(timezone.utc)
for d in (now.date(), (now + k.timedelta(days=1)).date()):
    print(d, "t120 ->", k.t120_for(d.isoformat()))
print("next event:", k.next_event(now))
