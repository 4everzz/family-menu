import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

scripts = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
for i, script in enumerate(scripts):
    js = "function __t(){ " + script + " }"
    fn = f"E:/AI/menu/chk_s{i}.js"
    with open(fn, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"Script {i+1}: {len(script)} chars -> {fn}")
