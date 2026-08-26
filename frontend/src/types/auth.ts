export type Role = "Content Creator" | "Learner" | "Educator" | "Administrator";

export interface CurrentUser {
  id: string;
  full_name: string;
  email: string;
  role_id: string;
  role: Role;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  email: string;
  role: Role;
}
