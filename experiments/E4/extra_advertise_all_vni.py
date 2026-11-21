"""E4 extra: remove `advertise-all-vni` on leaf2 and record the symptom matrix (not in the catalogue)."""
import json
import sys
import time

sys.path.insert(0, "src")
from fabricx import diagnose, model  # noqa: E402
from fabricx.faults import runner as fr  # noqa: E402
from fabricx.faults.catalogue import vty  # noqa: E402

f = model.load()
fr.wait_healthy(f)
vty(f, "leaf2", "router bgp 65002", "address-family l2vpn evpn", "no advertise-all-vni")
time.sleep(20)
d, _ = diagnose.diagnose(f)
res = {"fault": "no advertise-all-vni on leaf2", "symptoms": d.symptoms,
       "diagnosis": [x.to_dict() for x in d.primary], "consequences": [x.cause_key for x in d.consequences]}
vty(f, "leaf2", "router bgp 65002", "address-family l2vpn evpn", "advertise-all-vni")
fr.wait_healthy(f)
open("experiments/E4/extra_advertise_all_vni.json", "w").write(json.dumps(res, indent=1))
print(json.dumps(res, indent=1)[:1500])
