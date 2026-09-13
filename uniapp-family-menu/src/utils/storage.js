export function getStorage(key, fallback = null) {
  try {
    const value = uni.getStorageSync(key);
    return value === '' || value === undefined || value === null ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

export function setStorage(key, value) {
  try {
    uni.setStorageSync(key, value);
    return true;
  } catch (error) {
    return false;
  }
}

export function removeStorage(key) {
  try {
    uni.removeStorageSync(key);
    return true;
  } catch (error) {
    return false;
  }
}
