# 云环境配置说明

工作目录为 `/workspace/trade-forecast`，使用现有仓库，不需要新建 Git worktree。

后续配置已在恢复后的云环境中启动程序，访问 Google/Comtrade 成功，地图有限检索取得一条真实线索。新增 4 个隧道所需域名已保存为新草稿；免费隧道尚未建立。下文的初版说明作为历史记录保留，最新结果见 [本次配置结果](CONFIGURATION-STATUS.zh-CN.md)。

已在当前云机器执行安装脚本：固定版本的 Python 运行依赖、测试工具，以及 Google Workspace / Playwright 参考 CLI 安装成功；技能内容校验、应用测试和启动检查通过。应用使用系统 Chromium。开发用虚拟环境位于 `/workspace/scratch/trade-forecast-env`。

可复用配置包括 `install_script`（依赖安装和检查）、`start_skill`（启动与内部验证步骤）及 25 个所需网络域名。云环境配置工具已确认草稿保存成功，尚需发布。仓库成员、已有环境变量和秘密绑定保留。未写入 Gmail token、账号密码或接口密钥。

新增的网络域名用于 Google 地图/搜索与授权、Gmail API、官方统计、平台规则页面、浏览器下载和 Cloudflared 官方发布查询。域名清单见 [cloud-network-domains.json](cloud-network-domains.json)。原有包管理器网络预设保留。任意客户官网或展会域名需要按实际目标补充，未开放所有网站。

**下一步：**在云环境设置中检查并保存草稿，然后发布环境。保存草稿没有改变当前运行机器的访问权限；Google Maps 的访问限制仍未解除，也没有验证发布后或新任务中的恢复。

运行中的服务器、隧道与连接不会因保存草稿自动保留，后续任务应按启动说明重新启动，并再次验证实际访问。Windows 本机安装不依赖这些云环境步骤，请使用 [Windows 快速开始](QUICKSTART.zh-CN.md)。
