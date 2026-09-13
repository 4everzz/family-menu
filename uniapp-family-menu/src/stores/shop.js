import { defineStore } from 'pinia';
import { getStorage, setStorage, removeStorage } from '../utils/storage';
import { useCartStore } from './cart';

const CONTEXT_KEY = 'current_shop_context';

export const useShopStore = defineStore('shop', {
  state: () => ({
    context: getStorage(CONTEXT_KEY, null),
    loading: false,
  }),
  getters: {
    hasShop: (state) => Boolean(state.context?.shopId),
    shopId: (state) => state.context?.shopId || '',
    tableId: (state) => state.context?.tableId || '',
  },
  actions: {
    setContext(context) {
      const role = String(context?.role || 'customer');
      const accessMode = context?.accessMode === 'customer' ? 'customer' : (
        ['manager', 'store_admin', 'store_owner', 'store_staff', 'super_admin'].includes(role) ? 'staff' : 'customer'
      );
      const next = {
        shopId: String(context?.shopId || context?.id || ''),
        shopName: String(context?.shopName || context?.name || ''),
        role,
        accessMode,
        tableId: String(context?.tableId || ''),
        tableName: String(context?.tableName || ''),
        entryToken: accessMode === 'customer' ? String(context?.entryToken || '') : '',
        orderEntryMode: String(context?.orderEntryMode || 'store_entry'),
      };
      if (!next.shopId || !next.shopName) return false;
      const previous = this.context;
      const switchedShop = Boolean(previous?.shopId && previous.shopId !== next.shopId);
      const changedTable = Boolean(previous?.shopId === next.shopId && previous.tableId !== next.tableId);
      const confirmingFirstTable = changedTable && !previous?.tableId && Boolean(next.tableId);
      if (switchedShop || (changedTable && !confirmingFirstTable)) useCartStore().clear();
      this.context = next;
      setStorage(CONTEXT_KEY, next);
      return true;
    },
    clearContext() {
      this.context = null;
      removeStorage(CONTEXT_KEY);
    },
  },
});
