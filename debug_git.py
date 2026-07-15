import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Check git for what the ORIGINAL code was
import subprocess
try:
    result = subprocess.run(["git", "show", "HEAD:index.html"], capture_output=True, text=True, cwd="E:/AI/menu")
    if result.returncode == 0:
        original = result.stdout
        orig_scripts = re.findall(r"<script>(.*?)</script>", original, re.DOTALL)
        if len(orig_scripts) >= 2:
            orig_script2 = orig_scripts[1]
            # Find the keydown handler in the original
            orig_keydown_idx = orig_script2.find("keydown")
            if orig_keydown_idx >= 0:
                orig_end = orig_script2[orig_keydown_idx:]
                print("Original keydown handler:")
                print(repr(orig_end[:150]))
                
        # Find current keydown
        scripts = re.findall(r"<script>(.*?)</script>", content, re.DOTALL)
        if len(scripts) >= 2:
            curr_script2 = scripts[1]
            curr_keydown_idx = curr_script2.find("keydown")
            if curr_keydown_idx >= 0:
                curr_end = curr_script2[curr_keydown_idx:]
                print("\nCurrent keydown handler:")
                print(repr(curr_end[:150]))
    else:
        print("git show failed:", result.stderr)
except Exception as e:
    print(f"Error: {e}")
