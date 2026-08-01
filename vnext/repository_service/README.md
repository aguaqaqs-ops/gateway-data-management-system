# Gateway vNext Repository Service

当前状态：仅保留 Repository Service 的 DTO/settings skeleton，尚未实现业务服务。

以下能力当前均未实现：

- HTTP route、OpenAPI 和 client adapter；
- Dolt、persistence、repository layout、artifact upload/import 和 versioned read；
- P2-R1–R6 的全部 feature delivery。

本阶段不注册 stub route，不伪造 health/readiness 或 feature pass。真实 `/v1/` route、
OpenAPI 和 health behavior 只有在 P2-R1–R6 的真实纵切实现并通过集成测试后才会激活。
