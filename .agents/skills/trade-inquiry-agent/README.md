# Trade Inquiry Agent

> 外贸工厂询盘全流程 Agent — 自动化处理海外客户询盘，从解析到建档一站式完成

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.1-green.svg)

## 功能概览

| 步骤 | 工作流 | 说明 |
|------|--------|------|
| 1 | **询盘解析** | 提取客户信息、产品需求、数量、交期 |
| 2 | **可行性分析** | 评估产能、工艺要求、原材料供应 |
| 3 | **报价单生成** | 生成 FOB/CIF/EXW/佣金方案报价单 |
| 4 | **邮件起草** | 根据模板生成专业英文报价邮件 |
| 5 | **客户建档** | 创建客户档案，记录联系方式与偏好 |

## 快速开始

### 在 GitHub/ClawHub 安装

```bash
# 通过 ClawHub 安装
clawhub install trade-inquiry-agent

# 或从 GitHub 克隆
git clone https://github.com/AaronNee520/trade-inquiry-agent.git
```

### 使用示例

```
用户: 处理这个询盘
---
Agent: 请提供询盘内容（邮件/文本）
```

Agent 会自动完成全部 5 步工作流。

## 文件结构

```
trade-inquiry-agent/
├── SKILL.md                        # 主技能定义
├── references/
│   ├── email_templates.md          # 邮件模板
│   ├── quotation.md                # 报价单格式
│   └── product_classification.md   # 产品分类参考
└── README.md
```

## 参考资料

### 报价方案

- **FOB** (Free On Board) — 离岸价
- **CIF** (Cost, Insurance, Freight) — 到岸价
- **EXW** (Ex Works) — 工厂交货价
- **佣金方案** — 含代理佣金报价

### 产品分类

- 电子产品 (Electronics)
- 纺织服装 (Textiles & Apparel)
- 五金工具 (Hardware & Tools)
- 家居用品 (Home & Garden)
- 食品加工 (Food Processing)
- 包装印刷 (Packaging & Printing)

## ClawHub

![ClawHub](https://img.shields.io/badge/ClawHub-trade--inquiry--agent-purple)

查看 ClawHub 页面: https://clawhub.ai/trade-inquiry-agent

## License

MIT License
