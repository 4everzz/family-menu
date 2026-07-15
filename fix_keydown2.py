import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Current (broken): ccm()})}\n
# Should be: ccm()}})\n 
# Difference: The first } (close-if) should stay, the last } (extra) should go

# The pattern after my broken fix is: ccm()})}\n
# The correct pattern should be: ccm()}})\n

# So: change ccm()})}\n -> ccm()}})\n
old = "ccm()})}\n"
new = "ccm()}})\n"

if old in content:
    content = content.replace(old, new, 1)
    with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed correctly: ccm()}})}\n -> ccm()}})\n")
else:
    print(f"Pattern '{old}' not found!")
    # Check what we have
    idx = content.find("ccm()")
    if idx >= 0:
        print("Found ccm() at", idx)
        print("Chars after:", repr(content[idx+5:idx+15]))
