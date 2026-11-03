import sys
from pathlib import Path

# Add ignoAPI to path
igno_dir = Path(r"c:\Users\nagra\Desktop\updated_fleet\new_fleet_d\ignoAPI")
sys.path.insert(0, str(igno_dir))

from autoVDA import parse_vda_robots as auto_parse
from ignoAPI import parse_vda_robots as igno_parse

test_cases = [
    "rob5:VendorX:AGV-07, rob6:VendorY:AMR-02",
    "rob1:IGNOMAGINE:ROB-01; rob2:IGNOMAGINE:ROB-02",
    "rob3:VendorZ",
    "rob4",
    "",
    "   ",
    ["rob7:VendorA:SN1", "rob8:VendorB:SN2"],
    "rob9:MFR:SN9\nrob10:MFR:SN10",
    "rob5:VendorX:AGV-07, rob5:VendorX:AGV-07", # duplicate test
]

all_passed = True
for tc in test_cases:
    res1 = auto_parse(tc)
    res2 = igno_parse(tc)
    if res1 != res2:
        print(f"MISMATCH for '{tc}':\n  autoVDA: {res1}\n  ignoAPI: {res2}")
        all_passed = False
    else:
        print(f"MATCH: '{tc}' -> {res1}")

if all_passed:
    print("\nSUCCESS: All parse_vda_robots test cases match perfectly between autoVDA.py and ignoAPI.py!")
else:
    sys.exit(1)
