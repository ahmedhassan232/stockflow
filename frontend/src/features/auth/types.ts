export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  avatar_url: string | null;
  email_verified: boolean;
  is_platform_admin?: boolean;
}
export interface CompanyMembership {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  tenant_status: string;
  membership_status: string;
}
export interface ActiveCompany {
  tenant_id: string;
  name: string;
  slug: string;
  currency: string;
  timezone: string;
  role_code: string;
  role_name: string;
  permissions: string[];
  restricted_to_branches: boolean;
  branch_ids: string[];
}
export interface Me {
  user: User;
  memberships: CompanyMembership[];
  active_company: ActiveCompany | null;
}
export interface AuthPayload {
  access_token: string;
  expires_in: number;
  active_tenant_id: string | null;
  user: User;
  memberships: CompanyMembership[];
}
