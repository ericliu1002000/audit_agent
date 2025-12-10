from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List

from django.utils import timezone

from markdown import markdown
from xhtml2pdf import pisa

from indicator_audit.models import AuditFile


@dataclass
class FileReportPayload:
  """用于导出报告的标准化载体."""

  project_name: str
  department: str | None
  score: Any
  created_at: Any
  issues: List[Dict[str, Any]]


def _build_payload(audit_file: AuditFile) -> FileReportPayload:
  data: Dict[str, Any] = audit_file.report_json or {}
  project_name = (
      data.get("project_name")
      or audit_file.project_name
      or "未命名项目"
  )
  department = data.get("department") or audit_file.department
  score = data.get("score", audit_file.score)

  issues = data.get("issues") or []

  return FileReportPayload(
      project_name=project_name,
      department=department,
      score=score,
      created_at=audit_file.created_at or timezone.now(),
      issues=issues,
  )


def build_file_report_markdown(audit_file: AuditFile) -> str:
  """基于 AuditFile.report_json 构造 Markdown 报告内容."""

  payload = _build_payload(audit_file)

  lines: List[str] = []
  lines.append("# 财政支出绩效目标审核报告")
  lines.append("")
  lines.append(f"- **项目名称**：{payload.project_name}")
  if payload.department:
    lines.append(f"- **主管部门**：{payload.department}")
  lines.append(f"- **健康分**：{payload.score if payload.score is not None else '-'}")
  lines.append(
      f"- **审核时间**：{payload.created_at.strftime('%Y-%m-%d %H:%M')}"
  )
  lines.append("")

  groups = {
      "critical": [],
      "warning": [],
      "info": [],
  }
  for issue in payload.issues:
    sev = issue.get("severity")
    if sev == "critical":
      groups["critical"].append(issue)
    elif sev == "warning":
      groups["warning"].append(issue)
    else:
      groups["info"].append(issue)

  def append_group(title: str, desc: str, items: List[Dict[str, Any]]) -> None:
    lines.append(f"## {title}")
    if desc:
      lines.append("")
      lines.append(desc)
    if not items:
      lines.append("")
      lines.append("当前暂无该级别问题。")
      lines.append("")
      return
    for idx, issue in enumerate(items, start=1):
      issue_title = issue.get("title") or "问题"
      lines.append("")
      lines.append(f"### {idx}. {issue_title}")
      pos = issue.get("position")
      if pos:
        lines.append(f"- **定位**：{pos}")
      source = issue.get("source_label") or (
          "智能审查" if issue.get("source") == "ai" else "系统规则"
      )
      lines.append(f"- **来源**：{source}")
      issue_type = issue.get("issue_type")
      if issue_type:
        lines.append(f"- **问题类型**：{issue_type}")
      desc_text = issue.get("description")
      if desc_text:
        lines.append("")
        lines.append(desc_text)
      suggestion = issue.get("suggestion")
      if suggestion:
        lines.append("")
        lines.append(f"**整改建议**：{suggestion}")
    lines.append("")

  append_group(
      "红灯问题（禁止提交）",
      "必须立即整改，否则不可提交。",
      groups["critical"],
  )
  append_group(
      "黄灯问题（需人工复核）",
      "建议与业务负责人复核，确认风险后提交。",
      groups["warning"],
  )
  append_group(
      "蓝灯提示（优化建议）",
      "为优化建议，可结合实际情况选择采纳。",
      groups["info"],
  )

  return "\n".join(lines)


def render_markdown_to_pdf_bytes(markdown_text: str) -> bytes:
  """将 Markdown 文本转换为 PDF 字节流，不在磁盘落地."""

  html_body = markdown(markdown_text, output_format="html")
  html = f"""
  <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, "Microsoft Yahei", sans-serif; font-size: 12px; }}
        h1, h2, h3 {{ color: #0d6efd; }}
        ul, ol {{ padding-left: 1.2em; }}
      </style>
    </head>
    <body>
      {html_body}
    </body>
  </html>
  """
  pdf_io = BytesIO()
  pisa_status = pisa.CreatePDF(html, dest=pdf_io, encoding="utf-8")
  if pisa_status.err:
    raise ValueError("PDF 生成失败")
  return pdf_io.getvalue()


def build_file_report_pdf(audit_file: AuditFile) -> bytes:
  """生成单个审核文件的 PDF 报告字节流."""

  markdown_text = build_file_report_markdown(audit_file)
  return render_markdown_to_pdf_bytes(markdown_text)

