import sys
sys.stdout.reconfigure(encoding="utf-8")
with open("E:/AI/menu/index.html", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add CSS for the bottom cart bar (before .cart-overlay style)
old_css_marker = ".cart-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:200;display:none}"
new_css = ".cart-bar{position:fixed;bottom:0;left:0;right:0;z-index:150;background:#fff;box-shadow:0 -2px 12px rgba(0,0,0,0.1);display:none;align-items:center;padding:10px 20px;gap:12px;transition:transform 0.2s}.cart-bar.show{display:flex}.cart-bar .cb-icon{width:42px;height:42px;border-radius:50%;background:var(--primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:20px;position:relative;flex-shrink:0}.cart-bar .cb-icon .cb-badge{position:absolute;top:-4px;right:-4px;background:#e74c3c;color:#fff;font-size:10px;font-weight:700;min-width:16px;height:16px;border-radius:8px;display:none;align-items:center;justify-content:center;padding:0 3px}.cart-bar .cb-icon .cb-badge.show{display:flex}.cart-bar .cb-info{flex:1;min-width:0}.cart-bar .cb-info .cb-count{font-size:13px;color:#888}.cart-bar .cb-info .cb-total{font-size:18px;font-weight:800;color:var(--primary)}.cart-bar .cb-checkout{padding:10px 24px;border:none;border-radius:8px;background:linear-gradient(135deg,var(--primary),var(--primary-dark));color:#fff;font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap}.cart-bar .cb-checkout:disabled{opacity:0.5;cursor:not-allowed}.cart-bar .cb-checkout:hover{box-shadow:0 4px 12px rgba(192,57,43,0.3)}" + old_css_marker

if old_css_marker in content:
    content = content.replace(old_css_marker, new_css, 1)
    print("CSS added")
else:
    print("CSS marker not found!")
    if ".cart-overlay" in content:
        print("Found .cart-overlay at", content.find(".cart-overlay"))

# 2. Add HTML for cart bar (right before cart-overlay)
old_html_marker = '<div class="cart-overlay" id="cartOverlay">'
new_html = '<div class="cart-bar" id="cartBar"><div class="cb-icon"><span>🛒</span><span class="cb-badge" id="cartBarBadge">0</span></div><div class="cb-info"><div class="cb-count" id="cartBarCount">购物车是空的</div><div class="cb-total" id="cartBarTotal"></div></div><button class="cb-checkout" id="cartBarCheckout" disabled>去结算</button></div>' + old_html_marker

if old_html_marker in content:
    content = content.replace(old_html_marker, new_html, 1)
    print("HTML added")
else:
    print("HTML marker not found!")

# 3. Update the dish-list bottom padding to accommodate cart bar
old_dish_padding = ".dish-list{flex:1;overflow-y:auto;padding:12px 24px 100px}"
new_dish_padding = ".dish-list{flex:1;overflow-y:auto;padding:12px 24px 90px}"

if old_dish_padding in content:
    content = content.replace(old_dish_padding, new_dish_padding, 1)
    print("Dish padding updated")
else:
    print("Dish padding not found!")

with open("E:/AI/menu/index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("All changes applied")
