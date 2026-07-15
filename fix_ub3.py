import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Replace all remaining ub() with uba()
# But only when ub() is NOT part of another word
import re

# Pattern: ub() not preceeded by "a" (to avoid replacing "uba()" into "ubaa()")
content = re.sub(r'(?<!a)ub\(\)', 'uba()', content)

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

if "ub()" in content:
    print("WARNING: Still has ub()!")
    idx = content.find("ub()")
    while idx >= 0:
        print(f"  At {idx}: {repr(content[max(0,idx-5):idx+10])}")
        idx = content.find("ub()", idx+1)
else:
    print("OK: all ub() replaced with uba()")
