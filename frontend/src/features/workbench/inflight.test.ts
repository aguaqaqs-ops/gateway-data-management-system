import { describe, expect, it } from "vitest";
import { InflightGate } from "./inflight";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("InflightGate (FE4a C2)", () => {
  it("shares one run between rapid consecutive triggers", async () => {
    const gate = new InflightGate<string>();
    let calls = 0;
    const first = deferred<string>();
    const starter = (value: Promise<string> | string) => () => {
      calls += 1;
      return Promise.resolve(value);
    };
    const left = gate.run(starter(first.promise));
    const right = gate.run(starter("late"));
    expect(calls).toBe(1);
    expect(gate.inFlight).toBe(true);
    first.resolve("done");
    await expect(left).resolves.toBe("done");
    await expect(right).resolves.toBe("done");
    expect(gate.inFlight).toBe(false);
    // After settling, the next trigger starts a fresh run.
    await expect(gate.run(starter("next"))).resolves.toBe("next");
    expect(calls).toBe(2);
  });

  it("shares failures and releases the gate", async () => {
    const gate = new InflightGate<string>();
    let calls = 0;
    const failing = () => {
      calls += 1;
      return Promise.reject<string>(new Error("boom"));
    };
    const left = gate.run(failing);
    const right = gate.run(failing);
    await expect(left).rejects.toThrow("boom");
    await expect(right).rejects.toThrow("boom");
    expect(calls).toBe(1);
    expect(gate.inFlight).toBe(false);
    await expect(
      gate.run(() => {
        calls += 1;
        return Promise.resolve("recovered");
      }),
    ).resolves.toBe("recovered");
    expect(calls).toBe(2);
  });
});
