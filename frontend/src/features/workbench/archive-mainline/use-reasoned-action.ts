import { useState } from "react";

export interface ReasonedActionError {
  title: string;
  code: string;
}

/** One reasoned action (accept/revoke/close): target, reason, idempotency key, busy, error. */
export function useReasonedAction<T>() {
  const [target, setTarget] = useState<T | null>(null);
  const [reason, setReason] = useState("");
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ReasonedActionError | null>(null);

  function open(next: T) {
    setTarget(next);
    setReason("");
    setError(null);
    setKey(crypto.randomUUID());
  }

  return {
    target,
    setTarget,
    reason,
    setReason,
    key,
    setKey,
    busy,
    setBusy,
    error,
    setError,
    open,
  };
}
