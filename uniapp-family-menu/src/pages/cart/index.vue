<template>
  <view class="page-shell cart-page">
    <view v-if="cartStore.items.length" class="cart-list">
      <view v-for="item in cartStore.items" :key="item.cartKey" class="cart-card">
        <view class="cart-image" :style="{ background: item.color || '#fed7aa' }"><image v-if="item.imageUrl" :src="item.imageUrl" mode="aspectFill" /><text v-else>{{ item.emoji || '🍽️' }}</text></view>
        <view class="cart-copy"><text class="cart-name">{{ item.name }}</text><text v-if="item.options?.length" class="cart-options">{{ item.options.join('、') }}</text><text class="cart-price">¥{{ item.price }}</text></view>
        <view class="stepper"><button class="stepper-button secondary" @click="change(item.cartKey, -1)">−</button><text class="stepper-count">{{ item.quantity }}</text><button class="stepper-button" @click="change(item.cartKey, 1)">+</button></view>
      </view>
      <view class="remark-card"><text class="remark-label">订单备注</text><textarea v-model="remark" class="remark-input" maxlength="80" placeholder="例如：少辣、不要香菜" /></view>
    </view>
    <view v-else class="empty-state"><text class="empty-title">购物车还是空的</text><text class="empty-copy">去菜单里挑几道喜欢的菜吧</text><button class="back-button" @click="backToMenu">去点菜</button></view>
    <view v-if="cartStore.items.length" class="cart-footer"><view class="total-row"><text>合计</text><text class="total-value">¥{{ cartStore.total.toFixed(2) }}</text></view><view class="footer-actions"><button class="clear-button" @click="clearCart">清空</button><button class="submit-button" @click="goCheckout">去结算</button></view></view>
  </view>
</template>

<script setup>
import { ref } from 'vue';
import { onShow } from '@dcloudio/uni-app';
import { useCartStore } from '../../stores/cart';

const cartStore = useCartStore();
const remark = ref('');
onShow(() => { remark.value = String(uni.getStorageSync('uni_family_checkout_remark') || ''); });
function change(key, delta) { cartStore.changeQuantity(key, delta); }
function clearCart() { uni.showModal({ title: '清空购物车', content: '确定移除当前已选的全部菜品吗？', confirmText: '清空', confirmColor: '#DC2626', success: (result) => { if (result.confirm) { cartStore.clear(); remark.value = ''; uni.removeStorageSync('uni_family_checkout_remark'); } } }); }
function goCheckout() { uni.setStorageSync('uni_family_checkout_remark', remark.value); uni.navigateTo({ url: '/pages/checkout/index' }); }
function backToMenu() { uni.switchTab({ url: '/pages/menu/index' }); }
</script>

<style scoped>
.cart-page { padding-bottom: calc(280rpx + env(safe-area-inset-bottom)); }.cart-list { display: flex; flex-direction: column; gap: 16rpx; }.cart-card { display: flex; align-items: center; gap: 14rpx; padding: 18rpx; border: 2rpx solid #fee2e2; border-radius: 16rpx; background: #fff; box-shadow: 0 6rpx 18rpx rgba(69, 10, 10, .06); }.cart-image { width: 88rpx; height: 88rpx; flex: 0 0 88rpx; display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: 14rpx; font-size: 36rpx; }.cart-image image { width: 100%; height: 100%; }.cart-copy { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6rpx; }.cart-name { overflow: hidden; color: #450a0a; font-size: 30rpx; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }.cart-options { overflow: hidden; color: #78716c; font-size: 22rpx; text-overflow: ellipsis; white-space: nowrap; }.cart-price { color: #dc2626; font-size: 27rpx; font-weight: 700; }.stepper { width: 168rpx; flex: 0 0 168rpx; display: flex; align-items: center; justify-content: space-between; }.stepper-button { width: 58rpx; min-width: 58rpx; height: 58rpx; margin: 0; padding: 0; border-radius: 29rpx; background: #dc2626; color: #fff; font-size: 34rpx; font-weight: 700; line-height: 54rpx; }.stepper-button.secondary { background: #fee2e2; color: #b91c1c; }.stepper-count { min-width: 28rpx; text-align: center; color: #450a0a; font-size: 26rpx; font-weight: 700; }.remark-card { padding: 20rpx; border: 2rpx solid #fee2e2; border-radius: 16rpx; background: #fff; }.remark-label { display: block; margin-bottom: 12rpx; color: #450a0a; font-size: 28rpx; font-weight: 700; }.remark-input { width: 100%; min-height: 88rpx; padding: 12rpx 14rpx; border: 2rpx solid #fecaca; border-radius: 12rpx; background: #fffafa; color: #450a0a; font-size: 26rpx; box-sizing: border-box; }.empty-state { display: flex; flex-direction: column; align-items: center; gap: 14rpx; margin-top: 180rpx; text-align: center; }.empty-title { color: #450a0a; font-size: 36rpx; font-weight: 700; }.empty-copy { color: #78716c; font-size: 27rpx; }.back-button { width: 280rpx; min-width: 0; height: 86rpx; margin-top: 12rpx; padding: 0; border-radius: 14rpx; background: #dc2626; color: #fff; font-size: 29rpx; font-weight: 700; line-height: 86rpx; }.cart-footer { position: fixed; right: 24rpx; bottom: calc(24rpx + env(safe-area-inset-bottom)); left: 24rpx; z-index: 2; display: flex; flex-direction: column; gap: 16rpx; padding: 20rpx; border: 2rpx solid #fecaca; border-radius: 18rpx; background: #fff; box-shadow: 0 12rpx 28rpx rgba(69, 10, 10, .16); }.total-row { display: flex; justify-content: space-between; align-items: baseline; color: #7c2d12; font-size: 27rpx; font-weight: 700; }.total-value { color: #dc2626; font-size: 42rpx; }.footer-actions { display: flex; gap: 16rpx; }.clear-button, .submit-button { min-width: 0; height: 88rpx; margin: 0; padding: 0; border-radius: 14rpx; font-size: 29rpx; font-weight: 700; line-height: 88rpx; }.clear-button { flex: .75; border: 2rpx solid #fca5a5; background: #fff; color: #b91c1c; }.submit-button { flex: 1.45; background: #dc2626; color: #fff; }
</style>
