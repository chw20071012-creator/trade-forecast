# Foreign Trade Email Writer

A powerful CLI tool for generating personalized B2B cold email sequences. Designed for international trade professionals and sales teams who need effective, industry-specific outreach emails.

## Features

- **3-Email Progressive Sequence**: Connection → Value → Action (follows B2B sales funnel)
- **Industry-Specific Templates**: 6 built-in industries with tailored messaging
- **Pain Point Driven**: Automatically generates content based on customer pain points
- **English Output**: Professional business English suitable for global outreach
- **High-Converting Subject Lines**: 5 proven subject line formulas included
- **Gmail API Integration**: Send emails directly from your Gmail account (v2.1.0+)
- **Intelligence Hierarchy**: Three modes (Precise/Auto/Blind) based on available information

## Installation & Setup

### Step 1: Prerequisites

```bash
# Install Python 3.x
# Download from https://python.org

# Install required Python packages
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib requests

# Set Tavily API Key (for website research)
# Get key from: https://tavily.com
[Environment]::SetEnvironmentVariable("TAVILY_API_KEY", "your-api-key", "User")
```

### Step 2: Configure Gmail API

**Option A: Reuse existing credentials**
```powershell
# If you have foreign-trade-email-sorter configured, credentials will be auto-detected
```

**Option B: Create new credentials**
1. Visit https://console.cloud.google.com
2. Create project → Enable Gmail API
3. Create OAuth 2.0 Client ID (Desktop app)
4. Download `credentials.json` to `scripts/` folder

### Step 3: First Authorization

```powershell
# Run once to authorize
python scripts/gmail_sender.py --to "test@test.com" --subject "Test" --body "Hello"
# Browser will open, click "Allow"
```

See [SETUP.md](SETUP.md) for detailed instructions.

### Step 4: Quick Start

```bash
# For Windows (PowerShell)
.\scripts\run-workflow.ps1    # Complete workflow

# For Mac/Linux (Bash)
bash scripts/b2b-cold.sh
```

## Usage

### Windows (PowerShell)

```powershell
.\scripts\b2b-cold.ps1 <command> [options]
```

### Mac/Linux (Bash)

```bash
bash scripts/b2b-cold.sh <command> [options]
```

## Commands

| Command | Description |
|---------|-------------|
| `sequence` | Generate complete 3-email sequence |
| `first` | Email 1: Building connection (low pressure) |
| `second` | Email 2: Delivering value (pain point focused) |
| `third` | Email 3: Call to action (urgency + CTA) |
| `subject` | Generate high open-rate subject lines |
| `followup` | Follow-up email for non-responders |

## Gmail API Send Commands

| Command | Description |
|---------|-------------|
| `send-email.ps1` | Send email via Gmail API (PowerShell) |
| `gmail_sender.py` | Send email via Gmail API (Python) |

### Sending Emails via Gmail API

```powershell
# Method 1: PowerShell wrapper
.\scripts\send-email.ps1 -To "client@example.com" -Subject "Hello" -Body "Email content"

# Method 2: Python direct
python scripts/gmail_sender.py --to "client@example.com" --subject "Hello" --body "Email content"

# Method 3: Send from file
.\scripts\send-email.ps1 -To "client@example.com" -Subject "Hello" -BodyFile "email.txt"
```

### Prerequisites for Gmail Send

1. **Python 3.x** installed
2. **Install Google API libraries**:
   ```powershell
   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```
3. **Gmail API credentials**: Copy `credentials.json` from `foreign-trade-email-sorter` or create new one
4. **First authorization**: Run once to authorize, token will be saved automatically
| `help` | Show help information |

## Options

| Option | Description |
|--------|-------------|
| `-i, --industry` | Industry type (see supported industries below) |
| `-c, --company` | Target company name |
| `-co, --country` | Target country/region |
| `-p, --painpoint` | Customer pain point |
| `-v, --valueprop` | Your value proposition |
| `-s, --sender` | Sender name |
| `-sc, --sender-company` | Sender company name |

## Supported Industries

| Industry | Trigger Keywords | Typical Pain Points |
|----------|-----------------|---------------------|
| `textile` | textile, fabric, clothing | Quality inconsistency, long production cycles |
| `electronics` | electronics, electronic | Component shortages, long lead times |
| `packaging` | packaging, package | High costs, environmental concerns |
| `machinery` | machinery, machine, industrial | Equipment downtime, parts availability |
| `consumer` | consumer, retail, product | Supplier reliability, delivery delays |
| `general` | general (default) | Generic template for any industry |

## Examples

### Generate Complete Sequence

```powershell
.\scripts\b2b-cold.ps1 sequence `
  -i electronics `
  -c "Tech Solutions Inc" `
  -p "component shortages" `
  -v "reliable stock with 48hr delivery" `
  -s "David Chen" `
  -sc "Global Electronics Ltd"
```

### Generate Single Email

```powershell
# First email only (connection)
.\scripts\b2b-cold.ps1 first -i textile -c "Fashion Brand"

# Second email only (value)
.\scripts\b2b-cold.ps1 second -i packaging -p "high packaging costs"

# Third email only (action)
.\scripts\b2b-cold.ps1 third -i machinery -c "Industrial Corp"
```

### Generate Subject Lines

```powershell
.\scripts\b2b-cold.ps1 subject -i consumer
```

## The 3-Email Sequence Strategy

### Email 1: Building Connection
**Goal**: Low-pressure introduction, seek dialogue

- Opens with industry-specific compliment
- Introduces sender without hard selling
- Asks open-ended question
- Tone: Friendly, curious, respectful

### Email 2: Delivering Value
**Goal**: Show how you solve their pain point

- References specific pain point
- Lists concrete value propositions
- Includes social proof (30% improvement example)
- Soft CTA for a brief call

### Email 3: Call to Action
**Goal**: Create urgency and get response

- "Last email" framing creates urgency
- Recaps key benefits
- Easy opt-out option ("not now")
- Clear calendar/schedule CTA

## Sample Output

### Subject Lines
```
1. Quick question about your electronics sourcing
2. Solving component shortages for electronics companies
3. Tech Solutions + potential collaboration
4. Are you open to a quick chat about electronics?
5. Last try: electronics opportunity
```

### Email 1 (Connection)
```
Subject: Quick question about your electronics sourcing

Hi there,

I've been impressed by your company's innovation in the electronics space.

I'm David Chen from Global Electronics Ltd. We specialize in reliable 
components, competitive pricing, strict quality control.

I'm not trying to sell you anything today—I just wanted to introduce 
myself and see if there's an opportunity for us to connect.

Any thoughts?

Best regards,
David Chen
Global Electronics Ltd
```

## Why This Works

1. **Progressive Approach**: Follows the natural B2B sales cycle
2. **Industry Intelligence**: Each industry has tailored messaging
3. **Pain Point Focus**: Addresses real customer challenges
4. **Low Pressure**: Email 1 doesn't ask for a meeting
5. **Clear Exit**: Email 3 gives an easy "not now" option

## Customization

### Adding New Industries

Edit the `Get-Compliment`, `Get-Value`, and `Get-PainPoint` functions in the script:

```powershell
"medical" { 
    return "FDA-compliant devices, precision manufacturing..."
}
```

### Modifying Email Templates

Email templates are in the `Generate-Email1`, `Generate-Email2`, and `Generate-Email3` functions. Edit the `Write-Host` lines to customize.

## Requirements

- **Windows**: PowerShell 5.0+
- **Mac/Linux**: Bash 4.0+

## License

MIT License - feel free to use for personal or commercial projects.

## Contributing

Pull requests welcome! Especially:
- New industry templates
- Additional language support
- Improved subject line formulas

## Author

Created by Morment | For foreign trade professionals

## Acknowledgments

- Inspired by [Snov.io's cold email templates](https://snovio.cn/blog/email-outreach-templates/)
- Best practices from 10+ years of B2B foreign trade experience
- Designed specifically for international trade professionals
