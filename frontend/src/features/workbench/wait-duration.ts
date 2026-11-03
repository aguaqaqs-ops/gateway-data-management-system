/** Formats an elapsed wait using seconds under one minute and h/m/s above it. */
export function formatWaitDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  if (total < 60) return `${total} 秒`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;
  return hours > 0 ? `${hours} 小时 ${minutes} 分 ${remaining} 秒` : `${minutes} 分 ${remaining} 秒`;
}
