import { hasActiveSubscription, type Subscription } from '../billing/subscriptions.ts';

export function canAccessProject(
  member: { organizationId: string },
  project: { organizationId: string; archived: boolean },
  subscription: Subscription,
  now: number,
): boolean {
  return member.organizationId === project.organizationId
    && !project.archived
    && hasActiveSubscription(subscription, now);
}
