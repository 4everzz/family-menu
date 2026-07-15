import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Add localStorage.removeItem at init() start, before ld()
old = "function init(){ld();"
new = "function init(){try{localStorage.removeItem('menu_data')}catch(e){}ld();"

if old in content:
    content = content.replace(old, new, 1)
    with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("DONE: init() clears old localStorage now")
else:
    print("init() pattern not found!")
    idx = content.find("function init(){")
    if idx >= 0:
        print("Found:", repr(content[idx:idx+60]))
