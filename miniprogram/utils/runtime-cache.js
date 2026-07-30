// 仅在本次小程序运行期间使用的内存缓存，重启后自动清空。
const records = Object.create(null);
const pendingRequests = Object.create(null);

function readRuntimeCache(key, ttl) {
  const record = records[key];
  if (!record || Date.now() - record.savedAt > Number(ttl || 0)) return undefined;
  return record.data;
}

function writeRuntimeCache(key, data) {
  records[key] = { data, savedAt: Date.now() };
  return data;
}

function clearRuntimeCache(key) {
  delete records[key];
}

function clearRuntimeCacheByPrefix(prefix) {
  Object.keys(records).forEach((key) => {
    if (key.startsWith(prefix)) delete records[key];
  });
}

async function loadRuntimeCache(key, ttl, loader, force = false) {
  if (!force) {
    const cached = readRuntimeCache(key, ttl);
    if (cached !== undefined) return cached;
  }
  if (pendingRequests[key]) return pendingRequests[key];

  const request = Promise.resolve()
    .then(loader)
    .then((data) => {
      if (data !== undefined && data !== null) writeRuntimeCache(key, data);
      return data;
    })
    .finally(() => {
      delete pendingRequests[key];
    });
  pendingRequests[key] = request;
  return request;
}

module.exports = {
  readRuntimeCache,
  writeRuntimeCache,
  clearRuntimeCache,
  clearRuntimeCacheByPrefix,
  loadRuntimeCache,
};
