---
version: "2.1.0"
name: foreign-trade-email-writer
description: "B2B cold email sequence generator with Intelligence Hierarchy System and Gmail API integration. Generates personalized 3-email sequences and sends directly via Gmail."
author: Morment
homepage: https://github.com/yourusername/foreign-trade-email-writer
source: https://github.com/yourusername/foreign-trade-email-writer
---

# Foreign Trade Email Writer (Professional Edition)

B2B cold email sequence generator with **Intelligence Hierarchy System** and **Gmail API Integration** for foreign trade professionals.

## What's New in v2.1.0

- **Gmail API Integration**: Send emails directly from your Gmail account
- **Reuse Existing Auth**: Leverages `foreign-trade-email-sorter` credentials
- **One-Command Send**: Generate and send emails in one step

## Intelligence Hierarchy System

This tool implements a 3-tier intelligence system that adapts email content based on the information you have available:

| Mode | Trigger | Approach |
|------|---------|----------|
| **Precise** | `-c <company> -p <painpoint>` | Full personalization with known company/pain point |
| **Auto** | `-u <url>` | Auto-research from company URL |
| **Blind** | `-mail-only` | Generic outreach with industry trends |

## Three-Email Strategy

1. **Email 1**: Building Connection (low-pressure introduction)
2. **Email 2**: Delivering Value (address pain points with certificates)
3. **Email 3**: Call to Action (urgency + clear CTA)

## Quick Start

### Prerequisites

1. **Python 3.x** installed
2. **Google API libraries**: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`
3. **Tavily API Key**: Set `TAVILY_API_KEY` environment variable for website research
4. **Gmail credentials**: Copy `credentials.json` from `foreign-trade-email-sorter` or create new one
5. **First authorization**: Run once to authorize Gmail, token will be saved

See [SETUP.md](SETUP.md) for detailed setup instructions.

### Complete Workflow (Recommended)

```powershell
# Run the complete workflow script
.\scripts\run-workflow.ps1
```

This will guide you through:
1. **Select Mode**: Choose Precise/Auto/Blind
2. **Input Customer Info**: Website URL, company name, pain points, etc.
3. **Auto Research**: (Auto mode) Analyze website using Tavily API
4. **Generate Emails**: Create personalized 3-email sequence
5. **Send Email**: Send via Gmail API

### Manual Usage (PowerShell)

```powershell
# Generate and display emails
.\scripts\b2b-cold.ps1 sequence -mode precise -c "Tech Corp" -p "long lead times"

# Send email directly via Gmail
.\scripts\send-email.ps1 -To "client@example.com" -Subject "Hello" -Body "Email content"

# Or use Python directly
python scripts/gmail_sender.py --to "client@example.com" --subject "Hello" --body "Email content"
```

### Mac/Linux (Bash)

```bash
# Generate emails
bash scripts/b2b-cold.sh sequence -mode precise -c "Tech Corp" -p "long lead times"

# Send via Gmail API
python3 scripts/gmail_sender.py --to "client@example.com" --subject "Hello" --body "Email content"
```

## Commands

| Command | Purpose |
|---------|---------|
| `sequence` | Full 3-email sequence with intelligence mode |
| `first` | Email 1: Connection |
| `second` | Email 2: Value |
| `third` | Email 3: Action |
| `subject` | Subject lines only |
| `followup` | Follow-up email |
| `send` | Send queued emails via SMTP (PowerShell only) |
| `queue` | Show pending emails |
| `clear-queue` | Clear send queue |

## Gmail API Commands

| Command | Purpose |
|---------|---------|
| `send-email.ps1` | Send email via Gmail API (PowerShell) |
| `gmail_sender.py` | Send email via Gmail API (Python) |

## Options

| Option | Description | Example |
|--------|-------------|---------|
| `-i` | Industry | `textile`, `electronics`, `packaging`, `machinery`, `consumer`, `general` |
| `-c` | Target company | `"Fashion Brand Inc"` |
| `-co` | Country | `"USA"`, `"Germany"` |
| `-p` | Pain point | `"long lead time"` |
| `-v` | Value proposition | `"7-day fast delivery"` |
| `-s` | Sender name | `"Mike Zhang"` |
| `-sc` | Sender company | `"ABC Textile Co."` |
| `-u` | Target URL | `"www.targetclient.com"` (auto mode) |
| `--mail-only` | Blind mode | No specific info needed |

## Gmail API Setup

### Option 1: Reuse existing credentials (Recommended)

If you have `foreign-trade-email-sorter` configured:

```powershell
# Copy credentials
copy "..\foreign-trade-email-sorter\credentials.json" "scripts\"

# First run will authorize and save token
python scripts/gmail_sender.py --to "test@example.com" --subject "Test" --body "Hello"
```

### Option 2: Create new credentials

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select existing
3. Enable **Gmail API**
4. Create **OAuth 2.0 Client ID** (Desktop app)
5. Download `credentials.json` to `scripts/` folder

### First Authorization

On first run, the script will:
1. Open browser for Gmail authorization
2. Request permission to send emails
3. Save token to `scripts/token.json`

## Intelligence Modes

### Precise Mode (Path A)
Full personalization when you know:
- Customer name
- Company name
- Specific pain point

Uses reference-based hooks like "I've been following your company..."

### Auto Mode (Path B)
Auto-research from URL when you only have:
- Company website URL

The system will:
1. Fetch and analyze the website
2. Detect business type (manufacturer/distributor/retailer)
3. Identify industry from keywords
4. Match pain points from industry knowledge base

### Blind Mode (Path C)
Generic outreach when you only have:
- Email address
- Industry/Country

Uses industry-wide hooks like "Recent regulatory changes in {country} are affecting how {industry} companies approach..."

## Sending Emails

### Method 1: PowerShell Wrapper (Recommended)

```powershell
# Send single email
.\scripts\send-email.ps1 -To "client@example.com" `
    -Subject "Quick question about your sourcing" `
    -Body "Email content here..."

# Send from file
.\scripts\send-email.ps1 -To "client@example.com" `
    -Subject "Hello" `
    -BodyFile "email.txt"
```

### Method 2: Python Direct

```python
python scripts/gmail_sender.py \
    --to "client@example.com" \
    --subject "Quick question" \
    --body "Email content..."
```

### Method 3: Complete Workflow

```powershell
# 1. Generate email
.\scripts\b2b-cold.ps1 first -mode precise -c "Tech Corp" -p "long lead times" > email.txt

# 2. Send email
.\scripts\send-email.ps1 -To "client@example.com" -Subject "Hello" -BodyFile "email.txt"
```

## Supported Industries

- **textile**: Fabrics, fashion, sustainable materials
- **electronics**: Components, quality control, stock management
- **packaging**: Custom packaging, eco-friendly materials
- **machinery**: Industrial parts, OEM/ODM services
- **consumer**: Retail products, flexible MOQ
- **general**: Universal template

## Industry Knowledge Base

Each industry includes:
- Pain points for targeted messaging
- Relevant certifications (ISO 9001, CE, OEKO-TEX, etc.)
- Trending topics for modern outreach

## Full Examples

### Generate and Send (Precise Mode)

```powershell
# Generate
.\scripts\b2b-cold.ps1 sequence `
  -mode precise `
  -i textile `
  -c "Fashion Brand Inc" `
  -co "USA" `
  -p "quality inconsistency" `
  -v "7-day fast delivery" `
  -s "Mike Zhang" `
  -sc "ABC Textile Co."

# Send first email
.\scripts\send-email.ps1 `
  -To "client@fashionbrand.com" `
  -Subject "Quick question about your textile sourcing" `
  -Body "Hi there..."
```

### Auto Mode with Gmail Send

```powershell
# Generate
.\scripts\b2b-cold.ps1 sequence -mode auto -u "www.targetclient.com" -co "Germany"

# Send
.\scripts\send-email.ps1 -To "contact@targetclient.com" -Subject "Hello" -BodyFile "generated_email.txt"
```

## Requirements

- **Windows**: PowerShell 5.0+ or Python 3.x
- **Mac/Linux**: Bash 4.0+ or Python 3.x
- **Python packages**: `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
- **Gmail API credentials**: `credentials.json` in `scripts/` folder

## File Structure

```
foreign-trade-email-writer/
├── scripts/
│   ├── b2b-cold.ps1          # PowerShell email generator
│   ├── b2b-cold.sh           # Bash email generator
│   ├── gmail_sender.py       # Gmail API sender (NEW)
│   ├── send-email.ps1        # PowerShell wrapper for Gmail (NEW)
│   ├── settings.json         # SMTP settings (legacy)
│   └── credentials.json      # Gmail API credentials (optional)
├── SKILL.md                  # This file
├── README.md                 # Detailed documentation
└── CHANGELOG.md              # Version history
```

## Trigger Words

- 外贸开发信
- 外贸邮件
- 开发信
- cold email
- foreign trade email
- B2B outreach
- sales email
- email sequence
- 销售邮件
- 客户开发
- Gmail发送
- 发送邮件

## License

MIT License