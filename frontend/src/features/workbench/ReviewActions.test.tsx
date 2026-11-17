import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReviewActions } from "./ReviewActions";
import { TEST_REVIEW_FACTS } from "../dev/simulated-api";
import type { SafeReviewFacts } from "../api/client";

const RESULT_FAILURES = [
  { code: undefined, release: false }, // still loading or a network interruption
  { code: "NETWORK_ERROR", release: false },
  { code: "SCOPE_FORBIDDEN", release: false },
  { code: "HTTP_401", release: false },
  { code: "HTTP_404", release: false },
  { code: "BUNDLE_LOAD_FAILED", release: false },
  { code: "BUNDLE_INTEGRITY_MISMATCH", release: false },
  { code: "SUBMISSION_RESULT_UNAVAILABLE", release: true },
  { code: "SUBMISSION_RESULT_INTEGRITY_FAILURE", release: true },
];

function buttons(
  resultErrorCode: string | undefined,
  overrides: Partial<SafeReviewFacts> = {},
  bundleReady = false,
) {
  const host = document.createElement("div");
  host.innerHTML = renderToStaticMarkup(
    <ReviewActions
      submissionId="submission-1"
      facts={{ ...TEST_REVIEW_FACTS, ...overrides }}
      bundleReady={bundleReady}
      resultErrorCode={resultErrorCode}
      onFactsChanged={() => undefined}
      onReviewSettled={async () => false}
    />,
  );
  const controls = [...host.querySelectorAll<HTMLButtonElement>(".review-actions__buttons button")];
  return { host, withdraw: controls[0]!, reject: controls[1]!, approve: controls[2]! };
}

describe("unreadable submission review actions", () => {
  it.each(RESULT_FAILURES)(
    "keeps approval blocked and permits release only for $code",
    ({ code, release }) => {
      const { withdraw, reject, approve, host } = buttons(code);
      expect(approve.disabled).toBe(true);
      expect(reject.disabled).toBe(!release);
      expect(withdraw.disabled).toBe(!release);
      if (release) expect(host.textContent).toContain("比较结果无法读取，不能通过");
    },
  );

  it.each(["APPROVED", "REJECTED", "WITHDRAWN"] as const)(
    "retains the terminal %s barrier even with a recognized result failure",
    (status) => {
      const { withdraw, reject, approve } = buttons("SUBMISSION_RESULT_UNAVAILABLE", { status });
      expect([withdraw, reject, approve].every((button) => button.disabled)).toBe(true);
    },
  );

  it("retains the disposition barrier even with a recognized result failure", () => {
    const { withdraw, reject, approve } = buttons("SUBMISSION_RESULT_INTEGRITY_FAILURE", {
      submission_disposition: {
        submission_id: "submission-1",
        disposition: "ARCHIVED_BASELINE",
        source_kind: "ARCHIVE",
        result_id: "result-1",
        closure: null,
      },
    });
    expect([withdraw, reject, approve].every((button) => button.disabled)).toBe(true);
  });

  it("keeps all existing actions available for a readable pending result", () => {
    const { withdraw, reject, approve } = buttons(undefined, {}, true);
    expect([withdraw, reject, approve].every((button) => !button.disabled)).toBe(true);
  });
});
