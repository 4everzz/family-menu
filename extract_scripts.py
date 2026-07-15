import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Extract both scripts
scripts = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)

# Write to a temp JS file for Node.js syntax check
for i, script in enumerate(scripts):
    # Need to handle template literals and strings
    # For Node.js check, wrap in a function
    js_code = f"function __test_{i}(){{\n{script}\n}}"
    with open(f"E:/AI/menu/script_{i}.js", "w", encoding="utf-8") as f:
        f.write(js_code)
    print(f"Script {i+1}: {len(script)} chars written to script_{i}.js")
