const records = Object.create(null);
const pendingRequests = Object.create(null);

export function readRuntimeCache(key, ttl) {
  const record = records[key];
  if (!record || Date.now() - record.savedAt > Number(ttl || 0)) return undefined;
  return record.data;
}

export function writeRuntimeCache(key, data) {
  records[key] = { data, savedAt: Date.now() };
  return data;
}

export function clearRuntimeCache(key) {
  delete records[key];
}

export async function loadRuntimeCache(key, ttl, loader, force = false) {
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
