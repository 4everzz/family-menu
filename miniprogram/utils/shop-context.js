const { getCurrentShop, setCurrentShop } = require('./shop-store');
const { loadRuntimeCache } = require('./runtime-cache');

const SHOP_SNAPSHOT_CACHE_TTL = 10 * 1000;

function isStaffShop(shop) {
  return ['store_admin', 'store_owner', 'store_staff', 'super_admin'].includes(String(shop && shop.role || ''));
}

async function ensureCurrentShop() {
  let currentShop = getCurrentShop();
  if (currentShop && currentShop.id && (currentShop.accessMode === 'staff' || currentShop.entryToken)) return currentShop;
  let shops = [];
  if (currentShop && currentShop.id) {
    shops = [currentShop];
  }
  if (!shops.length) {
    const response = await wx.cloud.callFunction({
      name: 'shop-access',
      data: { action: 'listMyShops' },
    });
    const result = response.result || {};
    shops = result.ok && Array.isArray(result.shops) ? result.shops : [];
  }
  shops = shops.filter(isStaffShop);
  if (shops.length !== 1) throw new Error('当前店铺信息不可用');
  const response = await wx.cloud.callFunction({
    name: 'shop-access',
    data: { action: 'rejoinShop', shopId: shops[0].id },
  });
  const result = response.result || {};
  if (result.ok && result.shop && setCurrentShop(result.shop)) return result.shop;
  throw new Error(result.message || '暂时无法进入当前店铺');
}

async function callAdminMenu(action, payload = {}) {
  const shop = await ensureCurrentShop();
  const response = await wx.cloud.callFunction({
    name: 'admin-menu',
    data: { action, ...payload, shopId: shop.id, entryToken: shop.entryToken || '' },
  });
  return response.result || {};
}

async function getCurrentShopSnapshot(options = {}) {
  const shop = getCurrentShop();
  if (!shop || !shop.id) return { ok: false, code: 'SHOP_CONTEXT_REQUIRED' };
  const cacheKey = `shop-snapshot:${shop.id}:${shop.accessMode}:${shop.tableId || ''}:${shop.entryToken || ''}`;
  return loadRuntimeCache(cacheKey, SHOP_SNAPSHOT_CACHE_TTL, async () => {
    const response = await wx.cloud.callFunction({
      name: 'shop-access',
      data: {
        action: 'getCurrentShopSnapshot',
        shopId: shop.id,
        entryToken: shop.entryToken || '',
      },
    });
    return response.result || {};
  }, options && options.force === true);
}

module.exports = {
  ensureCurrentShop,
  callAdminMenu,
  getCurrentShopSnapshot,
};
