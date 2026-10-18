# 外贸工作台 · Trade Agent

用于箱包 OEM、茶叶 B2B 等外贸业务的本地工作台，集中管理客户、产品、市场资料、利润报价、邮件、订单和售后。AI 通过已配置的 ChatGPT Actions 接口参与分析与操作；安装软件不会自动完成账号连接或发送开发信。

## Windows 桌面版

[下载 Windows 10/11 64位桌面版](https://github.com/chw20071012-creator/trade-forecast/releases/tag/desktop-v0.2.0)

1. 下载 `TradeAgent-Desktop-0.2.0-Windows-x64.zip`，右键选择“全部解压”。
2. 打开 `TradeAgent` 文件夹，双击 **安装到桌面.cmd**。
3. 以后双击桌面上的 **外贸工作台**。软件内置 Python，无需手动安装依赖。

已有旧版资料时，先使用旧版 `stop.cmd` 停止程序。新版首次启动选择导入旧资料，再选择旧版文件夹。迁移复制资料、修正附件路径并保留原文件；未完成的发信审批需要重新核对。

业务资料保存在 `%LOCALAPPDATA%\TradeAgent\data`。升级软件不会覆盖该目录。关闭业务窗口后仍有后台服务，结束使用请在小控制窗口选择“退出工作台”。

桌面版使用系统 Edge/Chrome 的独立应用窗口，另有原生 Windows 控制窗口。软件没有商业代码签名。邮箱、Google Maps、GPT Actions 的真实连接结果需在自己的账号与网络环境中验证。

## 源码与复用

- `trade_agent/`：本地 API、业务存储和流程。
- `static/`：中文工作台界面。
- `desktop/`：Windows启动器、离线打包及安装入口。
- `.agents/skills/`：已整理的外贸参考技能；来源见 `skills.lock.json`。
- `templates/`：客户、产品和市场数据导入模板。
- `docs/`：获客、邮件、市场及 ChatGPT 接入说明。

运行与构建说明见 [desktop/README.md](desktop/README.md)；传统 Python 源码安装说明见 [docs/QUICKSTART.zh-CN.md](docs/QUICKSTART.zh-CN.md)。

演示数据为虚构资料；报价需要真实成本与行情输入。发信按确认的草稿版本执行，设置间隔与限额不等于承诺账号永不受限。
