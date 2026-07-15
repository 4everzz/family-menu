import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Check for any </script> inside JavaScript (not in HTML context)
# Only in the script blocks
import re
scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
for i, script in enumerate(scripts):
    if '</script>' in script:
        print(f'ERROR: Script block {i+1} contains literal </script>!')
    else:
        print(f'Script block {i+1}: OK (no </script> inside)')
    
    # Check for obvious JS syntax issues
    # Count braces
    opens = script.count('{')
    closes = script.count('}')
    if opens != closes:
        print(f'  WARNING: {opens} opens vs {closes} closes')
    else:
        print(f'  Braces: {opens} balanced')
    
    opens_p = script.count('(') 
    closes_p = script.count(')')
    if opens_p != closes_p:
        print(f'  WARNING: {opens_p} paren-opens vs {closes_p} paren-closes')
    else:
        print(f'  Parens: {opens_p} balanced')
    
    # Check for BOM
    if ord(script[0]) == 0xFEFF:
        print('  WARNING: BOM at start of script!')
    else:
        print(f'  First char: U+{ord(script[0]):04X}')
