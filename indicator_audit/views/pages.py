"""页面类视图：负责渲染 HTML 页面，不包含复杂业务逻辑。"""

from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from indicator_audit.models import AuditBatch, AuditFile
from indicator_audit.services.batch_summary_service import build_batch_summary


class AuditIndicatorPage(LoginRequiredMixin, TemplateView):
    """
    单文件智能审核页面。

    URL:
        /indicator_audit/audit/indicator/

    功能：
        - 提供上传单个 Excel 的表单。
        - 右侧显示实时执行日志与审核报告。
    """

    template_name = "indicator_audit/audit_indicator_table.html"


class AuditBatchPage(LoginRequiredMixin, TemplateView):
    """
    批量审核页面（按文件夹模式）。

    URL:
        /indicator_audit/audit/batch/

    功能：
        - 选择包含多个 Excel 的目录或多文件。
        - 创建审核批次并显示整体进度（总数/已完成/排队/失败）。
    """

    template_name = "indicator_audit/audit_batch.html"


class MyAuditFileListPage(LoginRequiredMixin, TemplateView):
    """
    我的审核记录列表页面。

    URL:
        /indicator_audit/my/files/

    功能：
        - 展示当前登录用户的历史审核文件列表。
        - 展示当前登录用户的历史审核批次列表。
        - 提供分页与跳转到详情页的入口。
    """

    template_name = "indicator_audit/my_audit_files.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        file_qs = AuditFile.objects.filter(created_by=self.request.user).order_by(
            "-created_at"
        )
        batch_qs = AuditBatch.objects.filter(created_by=self.request.user).order_by(
            "-created_at"
        )

        file_page_number = self.request.GET.get("file_page") or 1
        batch_page_number = self.request.GET.get("batch_page") or 1

        file_paginator = Paginator(file_qs, 10)
        batch_paginator = Paginator(batch_qs, 10)

        context["file_page_obj"] = file_paginator.get_page(file_page_number)
        context["batch_page_obj"] = batch_paginator.get_page(batch_page_number)
        return context


class AuditFileDetailPage(LoginRequiredMixin, TemplateView):
    """
    单个审核文件的历史报告详情页面。

    URL:
        /indicator_audit/file/<pk>/

    功能：
        - 读取 AuditFile.report_json。
        - 复用主审核页面的报告组件渲染红黄蓝灯详情。
    """

    template_name = "indicator_audit/audit_file_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        file_id = kwargs.get("pk")
        audit_file = get_object_or_404(
            AuditFile, pk=file_id, created_by=self.request.user
        )
        if not audit_file.report_json:
            raise Http404("该文件尚未生成审核报告。")
        context["audit_file"] = audit_file
        context["report_json"] = audit_file.report_json
        context["report_json_str"] = json.dumps(
            audit_file.report_json, ensure_ascii=False
        )
        return context


class AuditBatchDetailPage(LoginRequiredMixin, TemplateView):
    """
    批次详情页面（占位，用于后续统计大屏）。

    URL:
        /indicator_audit/batch/<pk>/

    当前功能：
        - 加载指定 AuditBatch 的统计汇总与基础信息。
        - 模板展示批次级大屏（资金盘子 / 健康度 / 问题分布 / 部门排行）。
    """

    template_name = "indicator_audit/audit_batch_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch_id = kwargs.get("pk")
        batch = get_object_or_404(AuditBatch, pk=batch_id, created_by=self.request.user)
        context["batch"] = batch
        summary = build_batch_summary(batch)
        context["batch_summary_json"] = json.dumps(summary, ensure_ascii=False)
        return context

