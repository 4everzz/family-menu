import { callCloudFunction } from './cloud';

export function callOrders(action, payload = {}) {
  return callCloudFunction('admin-menu', { action, ...payload });
}
