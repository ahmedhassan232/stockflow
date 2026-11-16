import { forwardRef, useId, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { cn } from "@/utils/cn";

const base =
  "h-10 w-full rounded-md border bg-card px-3 text-sm placeholder:text-muted-foreground disabled:opacity-50 aria-[invalid=true]:border-danger";

interface FieldProps {
  label: string;
  error?: string;
  hint?: string;
}

export const TextField = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & FieldProps>(
  ({ label, error, hint, className, id, ...props }, ref) => {
    const auto = useId();
    const fieldId = id ?? auto;
    return (
      <div className="space-y-1.5">
        <label htmlFor={fieldId} className="block text-sm font-medium">
          {label}
        </label>
        <input
          ref={ref}
          id={fieldId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-err` : hint ? `${fieldId}-hint` : undefined}
          className={cn(base, className)}
          {...props}
        />
        {error ? (
          <p id={`${fieldId}-err`} role="alert" className="text-xs text-danger">
            {error}
          </p>
        ) : hint ? (
          <p id={`${fieldId}-hint`} className="text-xs text-muted-foreground">
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);
TextField.displayName = "TextField";

export const SelectField = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & FieldProps>(
  ({ label, error, className, id, children, ...props }, ref) => {
    const auto = useId();
    const fieldId = id ?? auto;
    return (
      <div className="space-y-1.5">
        <label htmlFor={fieldId} className="block text-sm font-medium">
          {label}
        </label>
        <select ref={ref} id={fieldId} aria-invalid={error ? true : undefined} className={cn(base, className)} {...props}>
          {children}
        </select>
        {error ? (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
SelectField.displayName = "SelectField";
