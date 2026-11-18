import { useCallback, useState } from "react";
import type { GatewayApi, SafeReviewFacts } from "../../features/api/client";
import type { BrowseCommandRuntime } from "../../features/view-model/commands";
import { serverResultReleaseCode } from "./view-helpers";

export function useReviewFacts(gatewayApi: GatewayApi, runtime: BrowseCommandRuntime) {
  const [reviewFacts, setReviewFacts] = useState<SafeReviewFacts | null>(null);
  const [reviewResultChecking, setReviewResultChecking] = useState(false);
  const [reviewResultErrorCode, setReviewResultErrorCode] = useState<string>();

  // Facts remain authoritative even when the separately authorized result is unreadable.
  // Only failures from server summary/download requests can enable reject/withdraw;
  // local bundle identity and download failures never supply this permission.
  const readReviewContext = useCallback(
    async (submissionId: string) => {
      const [review, result] = await Promise.allSettled([
        gatewayApi.getReviewFacts(submissionId).then(
          (facts) => {
            gatewayApi.assertSession?.();
            if (runtime.snapshot.state.submissionId === submissionId) setReviewFacts(facts);
            return facts;
          },
          (cause: unknown) => {
            if (runtime.snapshot.state.submissionId === submissionId) setReviewFacts(null);
            throw cause;
          },
        ),
        gatewayApi.getSubmissionResult(submissionId),
      ]);
      gatewayApi.assertSession?.();
      if (review.status === "rejected") throw review.reason;
      if (result.status === "rejected") {
        const cause: unknown = result.reason;
        if (runtime.snapshot.state.submissionId === submissionId)
          setReviewResultErrorCode(serverResultReleaseCode(cause));
        throw cause;
      }
      return result.value;
    },
    [gatewayApi, runtime],
  );

  return {
    reviewFacts,
    setReviewFacts,
    reviewResultChecking,
    setReviewResultChecking,
    reviewResultErrorCode,
    setReviewResultErrorCode,
    readReviewContext,
  };
}
