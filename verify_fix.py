import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
checks = [
    ('甜品 escape', '\\u751c\\u54c1' in content),
    ('少吃辣 exists', '少吃辣' in content),
    ('爱吃辣 exists', '爱吃辣' in content),
    ('不吃香菜 exists', '不吃香菜' in content),
    ('remarkTags element', 'id="remarkTags"' in content),
    ('remarkInput element', 'id="remarkInput"' in content),
    ('cart-remark CSS', '.cart-remark{' in content),
    ('order-remark CSS', '.order-remark{' in content),
    ('order-remark in render', 'order-remark"' in content),
    ('remark in so()', 'remark:r' in content),
    ('single init', content.count('function init(){') == 1),
    ('no broken escape', '\\\\function init(){' not in content),
]
all_pass = True
for name, result in checks:
    status = 'PASS' if result else 'FAIL'
    if not result: all_pass = False
    print(f'  {status}: {name}')
if all_pass:
    print('ALL CHECKS PASSED')
else:
    print('SOME CHECKS FAILED - see above')
