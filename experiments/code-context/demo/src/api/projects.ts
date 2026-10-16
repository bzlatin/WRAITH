import { canAccessProject } from '../auth/permissions.ts';
import type { Subscription } from '../billing/subscriptions.ts';

export function getProject(
  member: { organizationId: string },
  project: { organizationId: string; archived: boolean; name: string },
  subscription: Subscription,
  now: number,
) {
  if (!canAccessProject(member, project, subscription, now)) return { status: 403 };
  return { status: 200, name: project.name };
}
