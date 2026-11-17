import { Button } from "../../design-system/components";

export function PreviewHeaderActions({
  withdrawEnabled,
  withdrawReason,
  withdrawRetry,
  withdrawRetryLabel,
  submitEnabled,
  submitReason,
  onWithdraw,
  onRetry,
  onSubmit,
}: {
  withdrawEnabled: boolean;
  withdrawReason?: string;
  withdrawRetry: boolean;
  withdrawRetryLabel: "刷新" | "重试读取";
  submitEnabled: boolean;
  submitReason?: string;
  onWithdraw: () => void;
  onRetry: () => void;
  onSubmit: () => void;
}) {
  // C3: the withdraw and submit disabled reasons render in their own
  // button-wrapped spans (see Button), separated by an explicit divider so
  // the two reasons never read as one sentence.
  return (
    <span className="compare-actions">
      <Button
        variant="danger"
        onClick={onWithdraw}
        disabled={!withdrawEnabled}
        disabledReason={withdrawReason}
      >
        撤回
      </Button>
      {withdrawRetry && (
        <button className="link-button" onClick={onRetry}>
          {withdrawRetryLabel}
        </button>
      )}
      {withdrawReason && submitReason && (
        <span className="compare-actions__divider" aria-hidden="true" />
      )}
      <Button
        variant="primary"
        onClick={onSubmit}
        disabled={!submitEnabled}
        disabledReason={submitReason}
      >
        提交
      </Button>
    </span>
  );
}
