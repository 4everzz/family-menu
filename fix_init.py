# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the init function and replace it with a properly encoded version
old_marker = "ra();const rmt=document.getElementById('remarkTags')"
idx = content.find(old_marker)
if idx > 0:
    # Find where the old broken tags started - go back to find the start of the init tag code
    init_start = content.rfind('function init(){', 0, idx)
    
    # Find the end of the init function
    rest_start = content.find('let st;', idx)
    
    if init_start > 0 and rest_start > init_start:
        # Build corrected init function
        new_init = "function init(){ld();const cc=document.getElementById('colorOptions');cc.innerHTML=CS.map(c=>'<div class=\"color-swatch\" data-color=\"'+c+'\" style=\"background:'+c+'\"></div>').join('');cc.querySelectorAll('.color-swatch').forEach(el=>el.addEventListener('click',()=>hc(el.dataset.color)));hc(CS[0]);ra();const rmt=document.getElementById('remarkTags');if(rmt){['少吃辣','爱吃辣','不吃香菜','少油','少盐','不要葱','加急'].forEach(t=>{const el=document.createElement('span');el.className='cr-tag';el.textContent=t;el.addEventListener('click',()=>{const inp=document.getElementById('remarkInput');const txt=t;if(el.classList.contains('active')){el.classList.remove('active');const tags=inp.value.split('\uFF1B').filter(x=>x.trim()&&x.trim()!==txt);inp.value=tags.join('\uFF1B')}else{el.classList.add('active');const existing=inp.value.trim();inp.value=existing?(existing+'\uFF1B'+txt):txt}inp.value=inp.value.trim()})})}}"
        
        content = content[:init_start] + new_init + content[rest_start:]
        
        with open('E:/AI/menu/index.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print('DONE: init() function fixed with proper tags')

# Verify
with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

if '少吃辣' in content:
    print('VERIFY: Tags present in file')
else:
    print('VERIFY: Tags STILL MISSING')

if content.count('function init(){') == 1:
    print('VERIFY: Single init()')
else:
    print('VERIFY: Multiple init() found:', content.count('function init(){'))
