import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Find the keydown handler exact position
idx = content.find("keydown")
if idx >= 0:
    snippet = content[idx-20:idx+120]
    print("Context around 'keydown':")
    print(repr(snippet))
    print()
    # Show each char
    for i, c in enumerate(snippet):
        if c in "{}()":
            print(f"  [{i}] char='{c}' code=U+{ord(c):04X}")
