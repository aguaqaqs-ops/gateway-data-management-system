import { useEffect, useState } from "react";
import type { UploadModeSnapshot } from "../../features/workbench/use-upload-mode";

export function useSubmitResume(uploadMode: UploadModeSnapshot) {
  const [resumeSubmitOperationId, setResumeSubmitOperationId] = useState<string | null>(null);
  // The resume card mounts as soon as the attempt is known, without waiting
  // for the (possibly long-polling) operation read inside the same refresh.
  const resumeAttemptOperationId = uploadMode.attempt?.operation_id ?? null;
  useEffect(() => {
    if (resumeAttemptOperationId) setResumeSubmitOperationId(resumeAttemptOperationId);
  }, [resumeAttemptOperationId]);
  return { resumeSubmitOperationId, setResumeSubmitOperationId };
}
