import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Find all remaining ub()
while True:
    idx = content.find("ub()")
    if idx < 0:
        break
    # Show context
    ctx = content[max(0,idx-20):idx+20]
    print(f"Found ub() at {idx}: {repr(ctx)}")
    
    # Check if it's part of uba()
    if content[idx-1:idx+5] != "buba(" and content[idx-1:idx+3] != "uba":
        # Replace ub() with uba() for function calls
        old = content[idx:idx+4]
        new = "uba()"
        content = content[:idx] + new + content[idx+4:]
        print(f"  Replaced with uba()")
    else:
        print(f"  Skipped (part of uba)")
    break  # Just fix one at a time

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

# Final check
if "ub()" in content:
    print("WARNING: Still has ub()")
    idx = content.find("ub()")
    print("Next at", idx, ":", repr(content[max(0,idx-10):idx+30]))
else:
    print("OK: all ub() replaced")
