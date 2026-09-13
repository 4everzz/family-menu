import { defineStore } from 'pinia';
import { getStorage, setStorage } from '../utils/storage';

const CART_KEY = 'uni_family_cart';

export const useCartStore = defineStore('cart', {
  state: () => ({
    items: getStorage(CART_KEY, []),
  }),
  getters: {
    count: (state) => state.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0),
    total: (state) => state.items.reduce((sum, item) => sum + Number(item.price || 0) * Number(item.quantity || 0), 0),
  },
  actions: {
    persist() {
      setStorage(CART_KEY, this.items);
    },
    clear() {
      this.items = [];
      this.persist();
    },
    add(dish, options = []) {
      const cartKey = `${dish.id}|${options.join('|')}`;
      const existing = this.items.find((item) => item.cartKey === cartKey);
      if (existing) {
        existing.quantity += 1;
      } else {
        this.items.push({ ...dish, cartKey, options, quantity: 1 });
      }
      this.persist();
    },
    changeQuantity(cartKey, delta) {
      const item = this.items.find((candidate) => candidate.cartKey === cartKey);
      if (!item) return false;
      item.quantity += Number(delta || 0);
      this.items = this.items.filter((candidate) => candidate.quantity > 0);
      this.persist();
      return true;
    },
    replace(items) {
      this.items = Array.isArray(items) ? items : [];
      this.persist();
    },
  },
});
