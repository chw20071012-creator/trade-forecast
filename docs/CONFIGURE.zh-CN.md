# 一键配置入口

在 Windows 10/11 上解压完整程序文件夹，安装 64 位 Python（推荐 3.12），然后**双击 `configure.cmd`**。它串行处理依赖、启动、本地演示、邮箱授权入口和 ChatGPT 连接入口，不需要依次手动运行四个脚本。

依赖已经可用时不重复安装。首次安装先跳过 Chromium 下载，获客可尝试电脑已有的 Chrome/Edge；没有可启动浏览器时再运行 `install.cmd` 下载 Chromium。跳过下载不表示浏览器已经安装或真实 Google Maps 已成功访问。

辅助脚本只对全新资料目录且没有客户的情况载入已授权的虚构演示。已有资料不会清空或重载；已有真实模式不会被强行改成演示模式，而是保留配置并打开网页供你继续操作。它不重置已审核的发信规则、不发邮件、不自动同步整个邮箱、不购买服务。

## Google Workspace 邮箱

邮箱账号仍需你本人在本机浏览器授权，AI 不需要你的邮箱密码。

- 没有 OAuth JSON 时，脚本打开 Google Cloud Console 和此说明。启用 Gmail API，配置同意屏幕（外部测试项目加入自己的企业邮箱为测试用户），创建 **Desktop app／桌面应用** OAuth 客户端并下载 JSON。
- 已经下载 JSON 时，在程序文件夹的终端运行：

  ```powershell
  .\configure.cmd -ClientJsonPath "C:\Users\你的用户名\Downloads\client_secret.json"
  ```

  脚本仅把选定的桌面 OAuth 配置保存到本地 `.runtime/data/secrets/gmail-client.json`，不会显示文件内容，也不会覆盖已有文件。随后打开官方 Google 授权页。回调成功后，在本地网页查看实际邮箱状态；打开授权页不代表已经接通。
- 若已有 OAuth token，脚本保留它；token 存在不等于本次已经验证真实邮箱可读。先在网页检查邮箱状态，再按指令同步。

如暂时只用演示，可运行 `configure.cmd -SkipMail`。首次真实发信仍需核实适用平台规则并批准完整草稿。

## ChatGPT Actions

辅助脚本调用现有连接脚本：从官方发布下载并校验 Cloudflared，创建免费临时 HTTPS 入口，在**本机控制台**显示 Action 私密密钥，再打开 GPT 编辑页与 Instructions。

你仍需在自己的私人 GPT 中完成：导入控制台显示的 schema URL，将密钥填入 **Actions → Authentication → API Key → Bearer**，粘贴 Instructions，然后调用状态接口实际测试。脚本不会代替你操作账号，也不会称为已经接通。

密钥只填认证框，不放到聊天、Instructions、公开截图或日志。窗口会保留，复制完成后再关闭。临时地址变化时需重新导入；电脑、程序和隧道都要运行。隧道失败时本地程序仍可用，按控制台结果处理，不把打开 GPT 页面当作连接成功。

暂时不配置 ChatGPT 时运行 `configure.cmd -SkipChatGPT`；只运行本地演示可用 `configure.cmd -SkipMail -SkipChatGPT`。更换端口可加 `-Port 8766`。

## 实际验证范围

这是用户电脑上的辅助入口，**尚未在 Windows 实机或 Windows PowerShell 5.1 中运行**。已用官方 PowerShell 7.6.6 的解析器在 Linux 中实际解析全部 6 个脚本，零语法错误；官方程序下载先完成 SHA256 校验，再用于解析，没有执行配置或授权。也已检查路径引用、参数传递、私密文件复制、不覆盖已有资料及脚本调用顺序。云环境的演示或平台连通结果不代表你的电脑、邮箱和 GPT 账号已经配置成功。

完整安装与授权细节见 [QUICKSTART.zh-CN.md](QUICKSTART.zh-CN.md)。出现错误时窗口保留并返回失败退出码；先看具体步骤，不需要重置数据或重新提供密码。
