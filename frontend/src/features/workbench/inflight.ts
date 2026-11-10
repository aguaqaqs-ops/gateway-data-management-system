/**
 * In-flight merge gate (FE4a C2).
 *
 * Rapid consecutive triggers share a single run instead of starting
 * concurrent read sequences. A caller that arrives while a run is in flight
 * joins the same promise; once the run settles, the next trigger starts a
 * fresh run. Failures are shared with all joiners and do not poison the gate.
 */
export class InflightGate<T> {
  private current: Promise<T> | null = null;

  run(task: () => Promise<T>): Promise<T> {
    const running = this.current;
    if (running) return running;
    const started: Promise<T> = task();
    this.current = started;
    const clear = () => {
      if (this.current === started) this.current = null;
    };
    started.then(clear, clear);
    return started;
  }

  get inFlight(): boolean {
    return this.current !== null;
  }
}
