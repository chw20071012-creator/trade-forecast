# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2026-03-27

### Added
- **Gmail API Integration**: Send emails directly from your Gmail account
- `gmail_sender.py`: Python script for sending emails via Gmail API
- `send-email.ps1`: PowerShell wrapper for easy Gmail sending
- Reuse existing auth from `foreign-trade-email-sorter`
- Automatic token management and refresh

### Changed
- Updated SKILL.md with Gmail API documentation
- Updated README.md with sending instructions
- Version bump to 2.1.0

## [2.0.0] - 2026-03-27

### Added
- Intelligence Hierarchy System with 3 modes:
  - **Precise Mode**: Full personalization with known company/pain point
  - **Auto Mode**: Auto-research from company URL
  - **Blind Mode**: Generic outreach with industry trends
- Industry knowledge base with pain points, certifications, trending topics
- SMTP integration framework
- Send queue management
- Optimal send time calculation based on timezone
- Industry-specific hooks and compliments

## [1.0.0] - 2026-03-18

### Added
- Initial release of Cold Email Writer
- 3-email progressive sequence generation (Connection → Value → Action)
- 6 built-in industries: textile, electronics, packaging, machinery, consumer, general
- Industry-specific compliments, value propositions, and pain points
- High open-rate subject line generation (5 formulas)
- Follow-up email for non-responders
- Cross-platform support: PowerShell (Windows) and Bash (Mac/Linux)
- Comprehensive documentation (README.md, SKILL.md)

### Features
- Pain point driven content generation
- Professional business English output
- Customizable sender and company information
- Support for target country specification
- Easy to extend with new industries

## Future Plans

- [ ] Add more industries (medical, automotive, food & beverage, etc.)
- [ ] Multi-language support (Chinese, Spanish, German, etc.)
- [ ] Integration with email sending APIs
- [ ] A/B testing subject line recommendations
- [ ] Email tracking and analytics integration
- [ ] Web UI for non-technical users
