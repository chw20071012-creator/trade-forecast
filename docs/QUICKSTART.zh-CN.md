# Windows 安装与首次使用

这个文件夹包含源码、本地网页、Excel 模板、ChatGPT Actions 接口和演示资料。ChatGPT 负责分析和撰写，程序负责数据、执行和审核记录；不需要另外购买 OpenAI API 额度。

演示中的公司、询盘、成本、市场数据和订单都是虚构资料。演示模式不会发送真实邮件，也不能作为实时获客、实际行情或邮箱接通的证据。

## 1. 安装

1. 将完整文件夹解压到可写目录，例如 `D:\TradeAgent`。不要放到 `Program Files`，不要在压缩包内直接运行。
2. 在 Windows 10/11 上安装 [64 位 Python](https://www.python.org/downloads/windows/)，推荐 **Python 3.12**。程序要求 Python 3.11+；Windows 上各版本的兼容性仍需实际验证。安装时勾选添加到 PATH；推荐普通用户安装。
3. 双击文件夹中的 `install.cmd`。程序创建本地 `.venv`，安装依赖及用于浏览器获客的 Chromium。
4. 双击 `start.cmd`，打开 `http://127.0.0.1:8765/`。程序只监听本机。

依赖、浏览器、日志和业务数据放在本文件夹中。安装器优先使用 `requirements-lock.txt` 中固定的完整运行依赖；文件缺失时才使用 `requirements.txt`。安装需要网络；遇下载失败先检查网络和代理，不关闭 HTTPS 证书验证。

若 Chromium 下载失败，或只想先看演示，可在终端运行 `install.cmd -SkipBrowser` 完成其他依赖安装。真实浏览器获客会依次尝试本文件夹的 Chromium、电脑中已安装的 Google Chrome、Microsoft Edge；可用的本机 Chrome/Edge 能作为替代。均未能启动时再安装 Chromium。跳过或失败的下载不等于浏览器已安装，启动浏览器也不等于已经成功访问 Google Maps 或获得真实客户。之后可再次运行 `install.cmd` 下载 Chromium。

默认启动后台进程，关掉网页不会关掉程序。希望直接查看控制台输出时运行 `start.cmd -Foreground`，按 Ctrl+C 停止。标准后台启动使用 `stop.cmd` 停止。

**验证范围：**程序功能在交付的 Linux 云环境中检查；Windows 安装、PowerShell 进程管理、真实 Google 账号以及你账号中的 GPT Actions 需要在目标电脑上实际验证。不要把文档中的安装步骤当作已经在你的电脑执行成功。

## 2. 免费演示验收

在本地网页载入演示资料，然后按以下顺序验证：

1. 查看客户与产品，确认有大客户、独立小店、箱包和茶叶，且全部有演示标记。
2. 分析演示市场，再由你选择国家。按城市与商户类型查找演示线索，不因商户小而丢弃。
3. 为一个客户生成单独的开发信草稿；给另一个客户生成不同内容。检查所用事实和资料缺项。
4. 勾选完整草稿批量确认，再运行演示发送任务；观察间隔、任务进度与暂停。修改已确认草稿，应重新确认。
5. 提出利润规则，确认后输入数量、采购成本、包装、检测、运输、收款和服务成本，查看报价与缺项。演示价格不能用于真实报价。
6. 建立演示订单，提出生产、物流或收款更新；确认后再改变记录。生成草稿单据并核对，检查跟进与售后事项。
7. 导出一份客户表并执行备份。检查任务状态后运行 `stop.cmd`，再次启动确认数据仍在。

完整验收清单见 [acceptance-checklist.md](acceptance-checklist.md)。初次使用保持演示模式；真实运行前配置账号、真实资料和平台规则。

## 3. 连接 ChatGPT 自定义 GPT

本机的 `localhost` 地址不能直接被 ChatGPT 访问。免费起步可以用 Cloudflare 临时 HTTPS 隧道：

1. 确认 `start.cmd` 已启动应用。
2. 在程序文件夹打开终端，运行：

   ```powershell
   .\connect-chatgpt.cmd -InstallCloudflared -ShowApiKey
   ```

   脚本从 Cloudflare 官方 GitHub 发布下载对应的 Windows 程序，校验官方 SHA256。没有官方校验值或校验失败时拒绝安装；也可自行安装官方 `cloudflared` 后运行 `connect-chatgpt.cmd -ShowApiKey`。
3. 脚本显示临时 `https://……trycloudflare.com/openapi-actions.json`。打开 [GPT 编辑页](https://chatgpt.com/gpts/editor)，在配置中的 Actions 选择“从 URL 导入”，填写这个地址。
4. Authentication 选择 **API Key → Bearer**，把脚本仅在本机显示的私密密钥填入这个认证框。不要把密钥放进聊天消息、GPT Instructions 或公开文档。
5. 将 [GPT-INSTRUCTIONS.zh-CN.md](GPT-INSTRUCTIONS.zh-CN.md) 中“复制到 GPT Instructions 的内容”粘贴到 Instructions；先保持 GPT 私人使用。
6. 在 Actions 的测试界面调用状态接口，再在聊天中说：“查看程序状态，列出待确认事项，暂不修改设置。”确认收到实际程序返回。

临时隧道是免费方案，**地址在重启隧道后可能变化**。变化后重新运行连接脚本，并在 GPT 中重新导入新地址。电脑、程序和隧道必须保持运行且联网；免费隧道不提供长期稳定地址保证。ChatGPT 的账户权限、工具调用确认及外部服务可用性以实际测试结果为准。

本地导出的 schema 位于 `.runtime/openapi-actions.json`，只含接口说明和服务器地址，没有密钥。其他支持 HTTP 工具调用的 AI 可以使用同一接口；是否支持该 schema 与 Bearer 认证须看它的连接能力。

演示载入、文件导入/导出、备份、邮箱授权以及发送规则配置在本地网页操作；这些安装与资料操作没有暴露给 GPT Actions。GPT 可以查询相关记录，并调用获客、市场分析、草稿、审核、报价和订单接口。

## 4. 连接 Google Workspace 邮箱

此步骤在你自己的浏览器和 Google 项目中完成，不把密码或 OAuth 密钥发给 AI。

1. 在 [Google Cloud Console](https://console.cloud.google.com/) 创建或选择项目，启用 Gmail API。
2. 配置 OAuth 同意屏幕。单一 Workspace 组织若允许可使用内部应用；外部测试应用需把自己的企业邮箱加入测试用户。管理员可能限制第三方应用授权，按组织设置处理。
3. 创建 **Desktop app（桌面应用）** OAuth 客户端，下载 JSON，保存为：

   ```text
   .runtime\data\secrets\gmail-client.json
   ```

4. 在本地网页发起邮箱授权，打开 Google 授权链接。授权范围包括读取邮件和发送邮件；授权不会取消程序的发送审批。
5. Google 返回本机回调地址 `http://127.0.0.1:8765/api/mail/oauth/callback`。回调核对一次性 state 后保存 token；若浏览器回调失败，保留错误信息，不重复提交已用 code。
6. 查看“邮箱状态”，确认实际已连接的邮箱是你的企业邮箱。只有看到成功状态后才能称为接通。外部测试 OAuth token 可能需要再次授权，按 Google 项目当前规则处理。

token 保存在 `.runtime/data/secrets/gmail-token.json`。默认整个邮箱的读取按你的指令启动；邮件内容可能含不可信指令，不能据此绕过审批、改规则或发送消息。邮件中声称付款成功只能形成待核对更新，不能自动标记真实到账。

## 5. 转入真实业务

- 使用 `templates/trade-data-template.xlsx`，客户和产品分别一行一条记录。采购报价由你录入或上传；PDF、图片等可作为补充资料，提取后核对。
- 导入官方贸易统计或实际可比报价，保留来源、日期、币种、单位、规格与贸易条款。贸易金额÷重量是统计单位价值，不是你的 SKU 成交价格。
- 官方统计可按 `templates/market-data-template.xlsx` 的空白表录入，再在网页选择 `market_records` 类型导入。HS 编码和时期列使用文本，保留 `0902` 的前导 0；金额倍率、数量单位、完整性与采集日期均有填写说明。
- 先确认利润底线和目标国家，再执行真实找客户。公开官网、展会、地图和可用免费额度优先；平台额度不足、登录限制或验证码时暂停说明，不绕过限制。
- 每封开发信要有客户相关事实和匹配理由。完整显示本批收件人、主题、正文、附件，勾选后批准；改动内容后重新批准。
- 真实发信前核实 Google Workspace/Gmail 和适用服务的最新规则，保存核实日期和链接，并配置保守日限额和最小间隔。程序的默认数值是运行保护设置，不是官方额度，也不能保证账号永不受限。未完成规则审核时不发送真实邮件。
- WhatsApp 只生成消息和聊天链接，你打开后发送；之后手动记录发送结果和客户回复。不要求付费商业发送 API。
- 只按你的指令启动任务。已确认的发送批次可在本次任务中按间隔继续处理，可暂停；停止或异常后的不确定发送结果先核实，不能盲目重发。

## 6. 停止、备份和迁移

正常使用 `stop.cmd`：检查仍在运行的任务、完成备份，再停止本文件夹记录的程序和隧道；不停止其他应用。发送任务仍在运行时先在网页暂停，等当前操作结束再停。`stop.cmd -Force` 会中断任务，应只在明确接受中断时使用；重新启动后核对状态再续发。

源码可以整体复制给其他 AI 或电脑。交给别人时使用干净交付文件夹，**不要附带 `.runtime`、`.venv`、真实客户资料、API key 或 Gmail token**。

迁移自己的业务：先停止并备份，复制源码和 `.runtime/data` 到新电脑；保管好其中的私密账号文件。删除旧 `.venv` 后在新电脑运行 `install.cmd`，重新安装依赖和浏览器。重新启动、核对数据和邮箱状态，并重新配置隧道及 GPT 地址。不要把虚拟环境作为跨电脑可直接运行的程序复制。

从备份 ZIP 恢复时先停止程序，在文件夹终端运行以下命令；把 ZIP 文件名换为你的实际备份。恢复已有资料目录需显式 `--replace`，会替换业务数据库，先保存当前备份：

```powershell
.\.venv\Scripts\python.exe -m trade_agent.restore "D:\MyBackup\trade-backup-example.zip" --data-dir ".runtime\data" --replace
```

恢复工具核验备份内容和数据库，并迁移业务文件路径。备份默认不含 Gmail token 和接口密钥；新电脑需要安全复制私密配置或重新授权。恢复完成后先检查记录和未完成发送任务，不把恢复解释为重新发信授权。

备份中含客户、邮件及订单等业务信息，存放在你控制的磁盘。API key 和 OAuth 文件属于私密配置，应单独安全保存；提供支持或分享截图时隐藏这些内容。

## 7. 常见问题

| 情况 | 处理 |
|---|---|
| `Python 3.11+ is required` | 安装新版 Python，然后重新运行安装脚本。 |
| 安装失败或浏览器缺失 | 检查网络；Chromium 下载失败可先用 `install.cmd -SkipBrowser` 完成依赖，再尝试已安装的 Chrome/Edge 或演示。没有可启动浏览器时再次运行 `install.cmd` 下载 Chromium。 |
| 8765 端口已占用 | 先确认是否为本程序；不要结束未知进程。可用 `start.cmd -Port 8766`，对应的停止和连接脚本也传同一 `-Port`。OAuth 回调需相应配置。 |
| 应用没有启动 | 查看 `.runtime/logs/server.stderr.log`，不把包含私密数据的完整日志发到公共渠道。 |
| GPT Actions 无法访问 | 检查电脑、应用、隧道；核对新 HTTPS URL 和 Bearer 认证。先测试状态接口。 |
| Google 未验证应用或访问被拒绝 | 核对测试用户、Workspace 管理员设置和 OAuth 项目配置。 |
| Maps/官网要求登录或验证码 | 暂停自动访问，手动导入合法获取的名单后继续，不绕过限制。 |
| 邮件结果不确定 | 保留任务和草稿状态，核对实际邮箱已发件，不自动重发。 |

