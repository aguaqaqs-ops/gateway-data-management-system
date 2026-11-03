export const OPERATION_STATUS_COPY = {
  QUEUED: "排队中",
  RUNNING: "执行中",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  SUPERSEDED: "已被新的操作取代",
  MANUAL_RECOVERY_REQUIRED: "需要管理员处理",
} as const;
