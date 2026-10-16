export type Subscription = {
  plan: 'trial' | 'paid';
  trialEndsAt: number;
  canceledAt?: number;
  paidThrough?: number;
};

export function hasActiveSubscription(subscription: Subscription, now: number): boolean {
  if (subscription.plan === 'trial') return now < subscription.trialEndsAt;
  return subscription.paidThrough !== undefined && now < subscription.paidThrough;
}
