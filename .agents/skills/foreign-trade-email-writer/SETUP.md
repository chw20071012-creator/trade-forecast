# 设置指南 - Foreign Trade Email Writer

> 完整配置指南，确保 skill 可以一键运行

---

## 📋 前置要求

### 1. 安装 Python 3.x

```powershell
# 检查是否已安装
python --version

# 如果未安装，从 https://python.org 下载安装
# 安装时勾选 "Add Python to PATH"
```

### 2. 安装 Google API 库

```powershell
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 3. 配置 Tavily API（用于网站调研）

```powershell
# 设置环境变量
[Environment]::SetEnvironmentVariable("TAVILY_API_KEY", "your-api-key", "User")

# 或者临时设置
$env:TAVILY_API_KEY = "your-api-key"
```

**获取 Tavily API Key：**
1. 访问 https://tavily.com
2. 注册账号
3. 获取 API Key

### 4. 配置 Gmail API 凭证

**选项 A：复用 foreign-trade-email-sorter 的凭证（推荐）**

```powershell
# 自动复用（已配置）
# 脚本会自动查找 foreign-trade-email-sorter 目录下的 credentials.json
```

**选项 B：创建新的 Gmail API 凭证**

1. 访问 https://console.cloud.google.com
2. 创建项目 → 启用 Gmail API
3. 创建 OAuth 2.0 Client ID（Desktop app）
4. 下载 `credentials.json`
5. 复制到 `scripts/` 目录

---

## 🚀 首次运行流程

### 第一步：授权 Gmail

```powershell
cd ~/.openclaw/workspace/skills/foreign-trade-email-writer

# 运行一次授权
python scripts/gmail_sender.py --to "test@test.com" --subject "Test" --body "Hello"
```

**会弹出浏览器窗口，点击"允许"授权发送邮件。**

授权成功后，会生成 `scripts/token.json`，后续无需再次授权。

---

## ✅ 验证配置

```powershell
# 测试生成邮件
.\scripts\b2b-cold.ps1 subject -i electronics

# 测试发送邮件（发给自己）
.\scripts\send-email.ps1 -To "your-email@gmail.com" -Subject "Test" -Body "Hello from skill"
```

---

## 🔧 故障排除

### 问题 1：Python 未找到
**解决：** 安装 Python 并添加到 PATH

### 问题 2：缺少 Google API 库
**解决：** `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`

### 问题 3：Tavily API Key 未设置
**解决：** 设置 `TAVILY_API_KEY` 环境变量

### 问题 4：Gmail 授权失败
**解决：** 
1. 删除 `scripts/token.json`
2. 重新运行授权

---

## 📁 文件结构

```
foreign-trade-email-writer/
├── scripts/
│   ├── b2b-cold.ps1          # 邮件生成器 (PowerShell)
│   ├── b2b-cold.sh           # 邮件生成器 (Bash)
│   ├── gmail_sender.py       # Gmail 发送器 (Python)
│   ├── send-email.ps1        # 发送包装器 (PowerShell)
│   ├── tavily_search.py      # 网站调研工具 (Python) [NEW]
│   ├── settings.json         # SMTP 配置
│   ├── credentials.json      # Gmail API 凭证 [需配置]
│   └── token.json            # Gmail 授权令牌 [自动生成]
├── SETUP.md                  # 本文件
├── SKILL.md                  # Skill 主文档
├── README.md                 # 详细文档
└── CHANGELOG.md              # 更新日志
```

---

## 📝 配置检查清单

- [ ] Python 3.x 已安装
- [ ] Google API 库已安装
- [ ] Tavily API Key 已设置
- [ ] Gmail API 凭证已配置（或已复用）
- [ ] 首次授权已完成
- [ ] 测试邮件发送成功

---

配置完成后，即可使用完整的开发信流程！
