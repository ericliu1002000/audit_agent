# Audit Agent Color Palette

记录“现代智能 - 科技蓝”配色方案，确保在任何工作会话中都能快速引用并保持一致性。

## 主色 (Primary)

- `--color-primary: #007BFF` – 科技蓝 (品牌 Logo、主要按钮、激活状态、图表主色)
- `--color-primary-darker: #0A58CA` – 深蓝备用 (悬停、强调)

## 中性色 (Neutrals)

- `--color-bg-main: #FFFFFF` – 主内容背景
- `--color-bg-secondary: #F8F9FA` – 侧栏 / 卡片标题背景
- `--color-text-primary: #212529` – 主文本 (标题、正文)
- `--color-text-secondary: #6C757D` – 次文本 (说明、标签)
- `--color-border: #DEE2E6` – 边框与分隔线 (输入框、表格、卡片)

## 点缀 / 状态色 (Accents / Status)

- `--color-success: #198754` – 成功 / 合规
- `--color-danger: #DC3545` – 危险 / 高风险 / 错误
- `--color-warning: #FFC107` – 警告 / 中风险 / 待处理
- `--color-info: #0DCAF0` – 信息提示 (需要时可使用主色代替)

```css
:root {
  --color-primary: #007BFF;
  --color-primary-darker: #0A58CA;
  --color-bg-main: #FFFFFF;
  --color-bg-secondary: #F8F9FA;
  --color-text-primary: #212529;
  --color-text-secondary: #6C757D;
  --color-border: #DEE2E6;
  --color-success: #198754;
  --color-danger: #DC3545;
  --color-warning: #FFC107;
  --color-info: #0DCAF0;
}
```

> 设计和开发涉及颜色时，请引用本文件或直接导入这些 CSS 变量，确保体验一致、专业、可信赖。
