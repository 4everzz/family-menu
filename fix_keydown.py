import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# The extra } is at position 81 from the keydown context:
# ccm()}})  -> should be ccm()})
# ccm()}})}  -> extra } at the end

# Fix: remove the extra } before \n
# Old pattern: ccm()}})}\n
# New pattern: ccm()})}\n

old = "ccm()}})}\n"
new = "ccm()})}\n"

if old in content:
    content = content.replace(old, new, 1)
    with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed: removed extra } from keydown handler")
else:
    print(f"Pattern '{old}' not found!")
    # Search for alternatives
    import re
    matches = list(re.finditer(r"ccm\(\)[^)]+", content))
    for m in matches:
        print(f"  Found: {repr(m.group())} at {m.start()}")
