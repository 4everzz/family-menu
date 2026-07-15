import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Check all uba() references
idx = 0
count = 0
while True:
    idx = content.find("uba()", idx)
    if idx < 0:
        break
    ctx = content[max(0,idx-30):idx+30]
    print(f"  uba() at {idx}: {repr(ctx[:60])}")
    idx += 1
    count += 1
print(f"Found {count} uba() references")

# Check for any ub() still present (should be none)
if "ub()" in content:
    print("WARNING: ub() still present!")
else:
    print("OK: ub() fully replaced")

# Check uba function definition
if "function uba()" in content:
    print("OK: uba() defined")
else:
    print("WARNING: uba() not defined!")
