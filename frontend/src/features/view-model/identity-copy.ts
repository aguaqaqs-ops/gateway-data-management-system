export function identityStatusText(value: unknown): string {
  if (value === "DIFFERENT_PROJECT") return "不同项目";
  if (value === "SAME_PROJECT") return "同一项目";
  if (value === "UNVERIFIABLE") return "项目身份无法验证";
  return "项目身份评估不可用";
}
