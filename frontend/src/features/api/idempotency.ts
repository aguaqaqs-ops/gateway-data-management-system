export interface IdempotentIntent<T> {
  key: string;
  request: T;
}

export function createIdempotentIntent<T>(request: T, createKey: () => string = () => crypto.randomUUID()): IdempotentIntent<T> {
  return { key: createKey(), request };
}
