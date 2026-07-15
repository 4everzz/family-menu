import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('E:/AI/menu/index.html', 'rb') as f:
    data = f.read()

# Check for BOM
if data[:3] == b'\xef\xbb\xbf':
    print('BOM STILL PRESENT!')
else:
    print('No BOM - good')

# Now read as text
text = data.decode('utf-8')

# Find script blocks
s1 = text.find('<script>')
s2 = text.find('</script>', s1)
s3 = text.find('<script>', s2)

first = text[s1+8:s2]
second = text[s3+8:-9]  # -9 for </script>

try:
    compile(first, '<first>', 'exec')
    print('First script: OK')
except SyntaxError as e:
    print('First script ERROR:', e)

try:
    compile(second, '<second>', 'exec')
    print('Second script: OK')
except SyntaxError as e:
    print('Second script ERROR:', e)
