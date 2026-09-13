import { callAdminMenu } from './admin-menu';

export function getCustomerMenu(context) {
  return callAdminMenu('getCustomerMenu', context);
}

export function createOrder(context, payload) {
  return callAdminMenu('createOrder', { ...context, ...payload });
}

export function listMyOrders(context) {
  return callAdminMenu('listMyOrders', context);
}

export function getMyOrder(context, id) {
  return callAdminMenu('getMyOrder', { ...context, id });
}
