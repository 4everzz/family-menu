import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the init function and debug the split chars
idx = content.find('function init(){')
end = content.find('let st;', idx)
body = content[idx:end]

split_idx = body.find("inp.value.split('")
if split_idx >= 0:
    # Get chars around the split
    chunk = body[split_idx:split_idx+50]
    print('Split context:')
    print(repr(chunk))
    # Check each char's unicode code point
    for i, c in enumerate(chunk):
        print(f'  [{i}] U+{ord(c):04X} = {c!r}')
else:
    print('Split not found')
    # Search for all occurrences
    for i, c in enumerate(body):
        if ord(c) > 127:
            print(f'  [{i}] U+{ord(c):04X} = {c!r}')
