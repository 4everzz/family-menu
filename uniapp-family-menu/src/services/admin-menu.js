import { callCloudFunction } from './cloud';

export function callAdminMenu(action, payload = {}) {
  return callCloudFunction('admin-menu', { action, ...payload });
}
