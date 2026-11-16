/** Mirrors the backend envelope (app/core/responses.py). */
export interface ApiSuccess<T> {
  success: true;
  data: T;
  message?: string | null;
}
export interface ApiErrorBody<D = unknown> {
  code: string;
  message: string;
  details?: D;
}
export interface ApiFailure<D = unknown> {
  success: false;
  error: ApiErrorBody<D>;
}
