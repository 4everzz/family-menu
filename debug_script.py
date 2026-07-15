import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

scripts = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
script = scripts[1]

# Write raw script (no wrapper) and check
with open("E:/AI/menu/script_1_raw.js", "w", encoding="utf-8") as f:
    f.write(script)

# Now find the issue by looking at the end of the script
# The script should end with: document.addEventListener('DOMContentLoaded',init);
last_100 = script[-100:]
print("Last 100 chars of script 2:")
print(repr(last_100))
print()

# Find the init() function specifically
idx = script.find("function init(){")
if idx >= 0:
    # Find the end of the init function - look for 'let st;'
    end_idx = script.find("let st;", idx)
    init_body = script[idx:end_idx]
    print(f"init() body ({len(init_body)} chars):")
    print(init_body)
    print()
    # Count braces
    opens = init_body.count("{")
    closes = init_body.count("}")
    print(f"init() braces: {opens} open, {closes} close")
