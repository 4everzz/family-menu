import { callCloudFunction } from './cloud';

export function callAuth(action, payload = {}) {
  return callCloudFunction('auth', { action, ...payload });
}

export function getCurrentUser() {
  return callAuth('getCurrentUser');
}
