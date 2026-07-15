import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Find the JavaScript section to modify
# Key functions to update:
# 1. ub() - update badge - need to also update cart bar
# 2. Add ucb() function - update cart bar

# First, let's add the ucb() function and update ub()
# Let me insert ucb() after the ub() function

old_ub = "function ub(){const b=document.getElementById('cartBadge'),c=cc();b.textContent=c>99?'99+':c;b.classList.toggle('show',c>0)}"

new_ub_and_bar = """function uba(){const c=cc(),t=ct(),b=document.getElementById('cartBadge'),cb=document.getElementById('cartBarBadge'),ccEl=document.getElementById('cartBarCount'),ctEl=document.getElementById('cartBarTotal'),ch=document.getElementById('cartBarCheckout'),bar=document.getElementById('cartBar');b.textContent=c>99?'99+':c;b.classList.toggle('show',c>0);if(cb){cb.textContent=c>99?'99+':c;cb.classList.toggle('show',c>0)}if(bar)bar.classList.toggle('show',c>0);if(ccEl)ccEl.textContent=c?('已选 '+c+' 件菜品'):'购物车是空的';if(ctEl)ctEl.textContent=c?'¥'+fp(t):'';if(ch)ch.disabled=!c}"""

if old_ub in content:
    content = content.replace(old_ub, new_ub_and_bar, 1)
    print("ub() updated to uba()")
else:
    print("ub() not found!")

# Also need to rename all calls to ub() to uba()
content = content.replace("ub();", "uba();")
print("ub() calls renamed to uba()")

# Also rename the function references in event listeners
# ub is referenced in addEventListener as well
print("Checking for ub references...")
if "uba()" in content:
    print("uba() calls present")

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
