import * as React from "react";

import { cn } from "@/lib/utils";

// A form field wrapper: a label sitting directly above the control, with an
// optional helper line below it. Keeps label/helper styling consistent across
// every input in a form instead of ad-hoc per-field markup.
type FieldProps = {
  label: string;
  /** Associates the <label> with a control rendered via `htmlFor`/`id`. */
  htmlFor?: string;
  /** Optional helper text rendered in a consistent muted style below. */
  hint?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
};

export function Field({ label, htmlFor, hint, className, children }: FieldProps) {
  return (
    <div className={cn("space-y-1", className)}>
      <label
        htmlFor={htmlFor}
        className="block text-xs font-medium text-foreground"
      >
        {label}
      </label>
      {children}
      {hint != null ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
