import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Fix the remaining ub() call in uq()
# Find: rc();ub()}  (where ub() should be uba())
old = "rc();ub()}"
new = "rc();uba()}"

if old in content:
    content = content.replace(old, new, 1)
    print("Fixed remaining ub() -> uba()")
else:
    print("Pattern not found!")
    # Search for the pattern
    idx = content.find("rc();ub()")
    if idx >= 0:
        print("Found ub() at", idx, ":", repr(content[idx-10:idx+20]))

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

# Verify no more ub()
if "ub()" in content:
    print("WARNING: ub() still present!")
    idx = content.find("ub()")
    print("At", idx, ":", repr(content[max(0,idx-10):idx+20]))
else:
    print("OK: all ub() replaced with uba()")
