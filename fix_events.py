import sys, re
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# Add event handlers for cart bar - add after the existing cart button handlers
# Looking for the cart button event listener registration
old_events = "document.getElementById('cartBtn').addEventListener('click',oc);document.getElementById('cartOverlay').addEventListener('click',cc2);document.getElementById('cartCloseBtn').addEventListener('click',cc2);document.getElementById('checkoutBtn').addEventListener('click',so)"

new_events = "document.getElementById('cartBtn').addEventListener('click',oc);document.getElementById('cartBarCheckout').addEventListener('click',oc);document.getElementById('cartBar').addEventListener('click',function(e){if(e.target.closest('button'))return;oc()});document.getElementById('cartOverlay').addEventListener('click',cc2);document.getElementById('cartCloseBtn').addEventListener('click',cc2);document.getElementById('checkoutBtn').addEventListener('click',so)"

if old_events in content:
    content = content.replace(old_events, new_events, 1)
    print("Cart bar event handlers added")
else:
    print("Old events not found!")
    idx = content.find("document.getElementById('cartBtn')")
    if idx >= 0:
        print("Found at", idx, ":", content[idx:idx+200])

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
