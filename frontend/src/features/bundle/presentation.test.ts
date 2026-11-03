import { describe, expect, it } from "vitest";
import type { RowDiffRecord } from "../view-model/model";
import { selectChangeRecordRows } from "./presentation";

describe("change record source selection", () => {
  it("preserves ordered moves when standard row records and comparison keys are both present", () => {
    const standard = [{ record_kind: "ROW_MODIFIED", row_identity: { parts: ["relay-1"] } } as unknown as RowDiffRecord];
    const ordered = [{ record_kind: "ORDERED_ROW_MOVED", row_identity: { parts: ["relay-1"] }, before_position: 2, current_position: 1 } as unknown as RowDiffRecord];
    expect(selectChangeRecordRows(standard, ordered, true).map((row) => row.record_kind)).toEqual(["ROW_MODIFIED", "ORDERED_ROW_MOVED"]);
  });

  it("uses ordered records as the row source when comparison keys are unavailable", () => {
    const standard = [{ record_kind: "ROW_MODIFIED" } as unknown as RowDiffRecord];
    const ordered = [{ record_kind: "ORDERED_ROW_MOVED" } as unknown as RowDiffRecord];
    expect(selectChangeRecordRows(standard, ordered, false)).toEqual(ordered);
  });
});
