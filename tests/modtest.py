import pirel.modifiers as pm
import pirel.pcells as pc
import pirel.sketch_tools as st

device_with_probe=pm.addOnePortProbe(pm.makeArray(pm.makeScaled(pc.FBERes),4),pc.GSGProbe)()

device_with_probe.anchor.n=1
device_with_probe.set_params({"AnchorSizeY":2})
device_with_probe.n_blocks=2

import pirel.sketch_tools as st

st.check(device_with_probe.draw(),joined=True)
