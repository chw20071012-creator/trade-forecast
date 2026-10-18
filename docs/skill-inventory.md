# 技能来源与集成清单

技能文件保存于 `.agents/skills/`，固定源提交和每个文件的 SHA-256 保存于 `skills.lock.json`。这些上游技能作为有来源的参考素材；首版业务程序已单独实现审核、获客、报价、订单和单据等模块，不直接开放上游的无审核发送脚本。不代表技能已经装进用户的 Windows 或普通 ChatGPT 聊天。

| 用户指定名称 | 实际保存的技能及来源 | 能力与限制 |
| --- | --- | --- |
| foreign-trade-leads | [同名技能](https://github.com/LeftenantZero/OpenClawSkillsMirror/tree/2bdbe764e68965e0c2257d1260618c0d6033c183/skills/xingfan0828/foreign-trade-leads) | Selenium/Chrome 尝试采集 Google Maps 商家名称、电话、地址、网站；脚本没有邮箱提取实现，线上效果未验证。发布者技能卡声明 MIT-0。 |
| customer-due-diligence | 未核实同名源；另存 [customer-due-diligence-report](https://github.com/cnproduct/customer-due-diligence-report-skill/tree/d13f7401f20faa3fb0e9b01bd9de4583ba650207) | MIT；公开资料尽调流程和实际 DOCX 生成器。搜索需要宿主提供。维护者自动提交/推送脚本未纳入安装。 |
| foreign-trade-email-writer | [同名镜像](https://github.com/Sisen-001/qclaw-skills/tree/6277f8c1dae0902d0bfb284ba10e98350288c872/growth/foreign-trade-email-writer) | MIT；邮件模板、Tavily 脚本与 Gmail 发送脚本。文档中的 PowerShell 包装缺失，默认模板包含未经验证的认证/市场宣称；仅作参考素材，需适配后使用。 |
| trade-inquiry-agent | [同名技能](https://github.com/AaronNee520/trade-inquiry-agent/tree/7fac4307e38751b02ddba1ee70a5b2c267765093) | 询盘解析、可行性、报价、邮件、建档 SOP。无执行代码或实时行情。README 声明 MIT，未提供完整 LICENSE 文件。 |
| check-trade-document-consistency | 未核实同名源；另存 [verify-docs](https://github.com/Dangooy/tianji-skills/tree/99ae9d2f6c6c6d41ec92a637d6298aa56d01fa91/verify-docs) | MIT；CI/PL 的 XLSX 对齐与核验规则及示例，无现成确定性校验 API。其他文件格式需另行实现。 |

## GitHub 补充

- [Google Workspace CLI skills](https://github.com/googleworkspace/cli)：Apache-2.0；Gmail 草稿/读信/回复、客户表格及共享配置，共 12 个相关技能目录。CLI 已固定为 `@googleworkspace/cli@0.22.5`。真实邮件和表格调用需要 Google 授权及网络访问。项目声明不是 Google 官方支持产品。
- [Playwright CLI skill](https://github.com/microsoft/playwright-cli)：Apache-2.0；官网和竞品网页研究。CLI 固定为 `@playwright/cli@0.1.22`；该 CLI 的真实外部网页研究未验证。首版独立使用 Python Playwright，本地 UI 已在真实浏览器演示；Chromium 下载与外部 Maps 访问另行记录，不能由 UI 通过推断外部获客成功。
- [mcp-builder](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills/mcp-builder)：Apache-2.0；供开发阶段构建可被 AI 调用的接口，不是现成的 ChatGPT 连接。

未采用 `Elvinaskill/foreign-trade-suite`：其 PolyForm Noncommercial 授权限制商业工作流，不能直接用于本项目的外贸业务。

上述 GWS 与 Playwright CLI 在云环境辅助目录中安装并做版本检查，不是 Windows 首版运行的硬性依赖。Windows 主程序按 `QUICKSTART.zh-CN.md` 安装 Python 运行依赖，可尝试本机 Chrome/Edge；ChatGPT 通过已实现的 HTTP Actions 接口调用，`mcp-builder` 仍只是开发参考，不表示已经提供 MCP 传输服务。

## 首版业务程序的执行规则

1. 收件人、主题、正文、附件及发送身份形成待审版本。用户确认该版本后才能发送；修改后重新确认。
2. 不把上游的直接发送脚本作为可绕过用户确认的 AI 工具。
3. 邮件引用的客户事实、认证、产能、交期和价格必须来自证据或用户资料。上游模板中的默认认证和市场宣称不得直接采用。
4. 单证校验按可执行代码实现，并区分通过、差异、缺字段和无法核验；不能把 AI 的一段总结当作确定性核验结果。
5. 查不到客户资料、网站访问失败或数据源不可用时，保留状态和原因，不伪造线索、邮箱或调查结论。
6. 授权和令牌放在技能源码之外；不复制维护者凭据、不运行维护者发布脚本。

## 上游素材验证

- 19 个技能目录、81 个文件的内容摘要及 frontmatter 检查通过。
- 8 个 Python 文件的语法解析、1 个 Bash 文件的语法检查通过；这不证明业务运行效果。
- 尽调报告生成器已用明确标注的合成测试资料生成 DOCX 并重新读取，包含正文及表格。
- GWS 0.22.5、Playwright CLI 0.1.22 的版本命令成功。
- Gmail 草稿的 dry-run 未完成：本云环境代理拒绝 `www.googleapis.com` 的 Discovery 请求。没有发送邮件，也没有完成邮箱授权或真实收发验证。
- 上游 Maps 脚本未作为真实获客验证，浏览器外部网页研究和实时行情也未验证；这些限制不否定首版独立模块的离线测试与本地 UI 验收。

## 首版集成验证

业务程序的离线测试与真实浏览器中的本地 UI 演示已通过，范围见 `acceptance-checklist.md`。真实 Google Maps 有限探测以 `paused_search_error` 暂停，错误为 `net::ERR_TUNNEL_CONNECTION_FAILED`，不能称为真实获客通过。Gmail OAuth 未配置，没有发送真实邮件；Windows 实机、实际 HTTPS 隧道及用户 GPT 账号连接尚未验证。第三方联系人 API 未配置，不把保存的 skill 或 schema 当作这些服务已接通的证据。

当前云环境进一步验证 Google 调用需要相应网络访问，例如 `www.googleapis.com`、`accounts.google.com`、`oauth2.googleapis.com`、`gmail.googleapis.com`。可复用安装/启动脚本与有限域名网络配置已保存为草稿，状态为 `saved`、`requires_publish=true`；尚未应用网络变更或发布，不能据此宣称真实服务已接通。详情见 `CLOUD-SETUP.zh-CN.md`。
