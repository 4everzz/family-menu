import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('E:/AI/menu/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_ld = "function ld(){try{const r=localStorage.getItem(SK);if(r){const d=JSON.parse(r);S.dishes=d.dishes||[];S.categories=d.categories||[];S.cart=d.cart||[];S.orders=d.orders||[]}else{S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}catch(e){S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}"

new_ld = "function ld(){try{const r=localStorage.getItem(SK);if(r){const d=JSON.parse(r);S.dishes=(d.dishes&&d.dishes.length)?d.dishes:JSON.parse(JSON.stringify(DC.dishes));S.categories=(d.categories&&d.categories.length)?d.categories:JSON.parse(JSON.stringify(DC.categories));S.cart=d.cart||[];S.orders=d.orders||[]}else{S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}catch(e){S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}"

if old_ld in content:
    content = content.replace(old_ld, new_ld)
    with open('E:/AI/menu/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('ld() updated successfully')
else:
    print('Old ld() not found - checking current state...')
    idx = content.find('function ld(){')
    if idx >= 0:
        end = content.find('function sd(){', idx)
        print(content[idx:end])
