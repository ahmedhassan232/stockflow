import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}

/** Native <dialog>: focus trap, Escape and backdrop come from the platform. */
export function Modal({ open, title, closeLabel, onClose, children, wide }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal?.();
    if (!open && el.open) el.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-label={title}
      className={`m-auto ${wide ? "w-[min(100%-2rem,52rem)]" : "w-[min(100%-2rem,28rem)]"} max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-lg border bg-card p-0 text-card-foreground shadow-xl backdrop:bg-primary/40`}
    >
      <div className="flex items-center justify-between border-b px-5 py-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <button type="button" onClick={onClose} aria-label={closeLabel} className="rounded-md p-1.5 hover:bg-muted">
          <X className="size-4" />
        </button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  );
}
