import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# New ld() that always loads dishes/categories from defaults, 
# but still preserves cart/orders from localStorage
new_ld = "function ld(){try{const r=localStorage.getItem('menu_data');if(r){const d=JSON.parse(r);S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=d.cart||[];S.orders=d.orders||[]}else{S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}catch(e){S.dishes=JSON.parse(JSON.stringify(DC.dishes));S.categories=JSON.parse(JSON.stringify(DC.categories));S.cart=[];S.orders=[]}}"

# Find and replace ld()
idx_ld = content.find("function ld(){")
idx_sd = content.find("function sd(){", idx_ld)
if idx_ld >= 0 and idx_sd > idx_ld:
    old_ld = content[idx_ld:content.find("}", content.find("}", idx_ld)+1)+1]
    # More robust: find the entire ld() function by counting braces
    brace_count = 0
    end_ld = idx_ld
    for i in range(idx_ld, len(content)):
        if content[i] == "{": brace_count += 1
        elif content[i] == "}": 
            brace_count -= 1
            if brace_count == 0:
                end_ld = i + 1
                break
    
    old_ld_content = content[idx_ld:end_ld]
    print("Old ld():", old_ld_content[:80], "...")
    print("New ld():", new_ld[:80], "...")
    
    content = content.replace(old_ld_content, new_ld, 1)
    with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("DONE: ld() now always loads dishes/categories from defaults")
else:
    print("ld() not found!")
