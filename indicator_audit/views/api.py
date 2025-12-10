"""JSON / 文件导出 API 视图。

本模块仅包含与前端交互的接口层，具体业务逻辑下沉到 services 中实现。
"""

from __future__ import annotations

import json
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from indicator_audit.models import AuditBatch, AuditFile
from indicator_audit.services import audit_file_service, batch_service
from indicator_audit.services.batch_summary_service import build_batch_summary
from indicator_audit.services.report_export_service import (
    build_file_report_markdown,
    build_file_report_pdf,
)
from indicator_audit.tasks import run_audit_task


def _init_task_status(task_id: str) -> None:
    """
    初始化单文件审核任务的状态缓存。

    作用：
        - 在 Redis/缓存中写入一条初始记录，状态为 pending。
        - 供前端轮询 /indicator_audit/api/audit/status/<task_id>/ 使用。
    """

    cache.set(
        f"audit_task_{task_id}",
        {
            "status": "pending",
            "logs": [{"status": "pending", "message": "任务排队中..."}],
        },
        timeout=60 * 60,
    )


@require_http_methods(["POST"])
def audit_upload(request):
    """
    单文件审核上传 API。

    URL:
        POST /indicator_audit/api/audit/upload/

    功能：
        - 接收前端上传的单个 Excel（字段名 file 或 excel_file）。
        - 将文件保存到 MEDIA_ROOT。
        - 创建一条初始的 AuditFile 记录（status=pending）。
        - 触发 Celery 审核任务，并返回 task_id 与 audit_file_id。
    """

    uploaded_file = request.FILES.get("file") or request.FILES.get("excel_file")
    if not uploaded_file:
        return JsonResponse(
            {"error": "请上传 Excel 文件"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    original_filename = uploaded_file.name or ""
    file_size = int(getattr(uploaded_file, "size", 0) or 0)
    user = request.user if request.user.is_authenticated else None

    # 1) 文件落盘并计算指纹（同一内容只在磁盘保存一次）
    file_path, relative_path, file_hash = audit_file_service.save_uploaded_file(
        uploaded_file
    )

    # 2) 尝试复用历史审核结果（秒审）
    task_id = uuid4().hex
    source_file = audit_file_service.find_reusable_source_file(file_hash)
    if source_file is not None:
        # 基于历史结果创建一条新的 AuditFile 记录
        audit_file = audit_file_service.create_reused_audit_file(
            user=user,
            batch=None,
            original_filename=original_filename,
            file_size=file_size,
            relative_path=relative_path,
            file_hash=file_hash,
            source_file=source_file,
        )
        # 直接写入“秒审完成”的任务状态与报告结果
        cache.set(
            f"audit_task_{task_id}",
            {
                "status": "completed",
                "logs": [
                    {
                        "status": "processing",
                        "message": "检测到相同文件内容，已复用历史审核结果（秒审）。",
                    },
                    {
                        "status": "completed",
                        "message": "审核完成（本次未重复调用 AI）。",
                    },
                ],
                "result": source_file.report_json,
            },
            timeout=60 * 60,
        )
        return JsonResponse(
            {"task_id": task_id, "audit_file_id": audit_file.id},
            json_dumps_params={"ensure_ascii": False},
        )

    # 3) 首次出现的文件，正常走 Celery 审核流程
    audit_file = audit_file_service.create_audit_file_for_upload(
        user=user,
        batch=None,
        original_filename=original_filename,
        file_size=file_size,
        relative_path=relative_path,
        file_hash=file_hash,
    )
    _init_task_status(task_id)
    run_audit_task.delay(file_path, task_id, audit_file.id)

    return JsonResponse(
        {"task_id": task_id, "audit_file_id": audit_file.id},
        json_dumps_params={"ensure_ascii": False},
    )


@require_http_methods(["GET"])
def audit_status(request, task_id: str):
    """
    单文件审核任务状态查询 API。

    URL:
        GET /indicator_audit/api/audit/status/<task_id>/

    功能：
        - 从缓存中读取指定 task_id 的当前状态、日志与最终结果。
        - 前端轮询该接口以刷新执行日志与审核报告。
    """

    data = cache.get(f"audit_task_{task_id}")
    if not data:
        return JsonResponse(
            {"error": "任务不存在或已过期"},
            status=404,
            json_dumps_params={"ensure_ascii": False},
        )

    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


@login_required
@require_http_methods(["POST"])
def api_create_batch(request):
    """
    创建审核批次 API。

    URL:
        POST /indicator_audit/api/batch/

    请求：
        JSON 结构：
            - batch_name: str，批次名称（通常为目录名）
            - description: str|null，可选说明

    功能：
        - 根据当前用户与批次名创建或复用 AuditBatch。
        - 返回批次的基础信息，用于后续上传文件与展示进度。
    """

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "请求体必须是合法的 JSON。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    batch_name = (payload.get("batch_name") or "").strip()
    description = (payload.get("description") or "").strip() or None

    if not batch_name:
        return JsonResponse(
            {"error": "批次名称不能为空。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    try:
        batch = batch_service.create_batch(request.user, batch_name, description)
    except ValueError as exc:
        return JsonResponse(
            {"error": str(exc)},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    return JsonResponse(
        {
            "id": batch.id,
            "batch_name": batch.batch_name,
            "status": batch.status,
            "total_files": batch.total_files,
        },
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@require_http_methods(["POST"])
def api_batch_upload(request, batch_id: int):
    """
    批次多文件上传 API。

    URL:
        POST /indicator_audit/api/batch/<batch_id>/upload/

    请求：
        multipart/form-data:
            - files: 多个 .xlsx 文件。

    功能：
        - 为指定批次创建多条 AuditFile 记录。
        - 为每个文件落盘、创建审核任务，并返回对应的 audit_file_id 与 task_id。
    """

    batch = get_object_or_404(
        AuditBatch, pk=batch_id, created_by=request.user
    )

    files = request.FILES.getlist("files")
    if not files:
        return JsonResponse(
            {"error": "请至少上传一个 Excel 文件。"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    created_files = []
    reused_files = []
    results = []

    for uploaded_file in files:
        original_filename = uploaded_file.name or ""
        file_size = int(getattr(uploaded_file, "size", 0) or 0)

        file_path, relative_path, file_hash = audit_file_service.save_uploaded_file(
            uploaded_file
        )

        # 1) 批次内部去重：若本批次已存在同一 file_hash，则直接跳过，不再计数
        existing_in_batch = audit_file_service.find_existing_in_batch_by_hash(
            batch, file_hash
        )
        if existing_in_batch is not None:
            results.append(
                {
                    "audit_file_id": existing_in_batch.id,
                    "task_id": None,
                    "original_filename": original_filename,
                    "skipped": True,
                }
            )
            # 不创建新记录、不触发 Celery，也不计入本次批次新增文件集合
            continue

        # 2) 跨批次结果复用：尝试从历史记录中秒审
        source_file = audit_file_service.find_reusable_source_file(file_hash)

        if source_file is not None:
            # 复用历史结果，不触发 Celery
            audit_file = audit_file_service.create_reused_audit_file(
                user=request.user,
                batch=batch,
                original_filename=original_filename,
                file_size=file_size,
                relative_path=relative_path,
                file_hash=file_hash,
                source_file=source_file,
            )
            task_id = None
            reused_files.append(audit_file)
        else:
            # 首次出现，正常触发 Celery 审核
            audit_file = audit_file_service.create_audit_file_for_upload(
                user=request.user,
                batch=batch,
                original_filename=original_filename,
                file_size=file_size,
                relative_path=relative_path,
                file_hash=file_hash,
            )
            task_id = uuid4().hex
            _init_task_status(task_id)
            run_audit_task.delay(file_path, task_id, audit_file.id)

        created_files.append(audit_file)
        results.append(
            {
                "audit_file_id": audit_file.id,
                "task_id": task_id,
                "original_filename": original_filename,
            }
        )

    # 更新批次统计信息：先挂接所有文件，再对“秒审”文件标记为已完成
    all_files = created_files + reused_files
    if all_files:
        batch_service.attach_files(batch, all_files)
    for reused_file in reused_files:
        batch_service.mark_file_finished(reused_file, success=True)

    return JsonResponse(
        {"batch_id": batch.id, "files": results},
        json_dumps_params={"ensure_ascii": False},
    )


@login_required
@require_http_methods(["GET"])
def api_batch_progress(request, batch_id: int):
    """
    批次进度查询 API。

    URL:
        GET /indicator_audit/api/batch/<batch_id>/progress/

    功能：
        - 基于 AuditFile 的实时聚合统计该批次下的文件执行情况。
        - 返回总文件数、已完成数、失败数、排队数与批次状态。
    """

    batch = get_object_or_404(
        AuditBatch, pk=batch_id, created_by=request.user
    )
    progress = batch_service.get_batch_progress(batch.id)

    # 将 datetime 转换为可序列化字符串
    data = {
        **progress,
        "created_at": progress["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        if progress.get("created_at")
        else None,
        "updated_at": progress["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        if progress.get("updated_at")
        else None,
    }

    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


@login_required
@require_http_methods(["GET"])
def api_batch_summary(request, batch_id: int):
    """
    批次统计大屏数据 API。

    URL:
        GET /indicator_audit/api/batch/<batch_id>/summary/

    功能：
        - 汇总指定批次的资金盘子、健康度、问题分布、部门排名等统计信息。
        - 供批次大屏页面渲染使用。
    """

    batch = get_object_or_404(
        AuditBatch, pk=batch_id, created_by=request.user
    )
    summary = build_batch_summary(batch)
    return JsonResponse(summary, json_dumps_params={"ensure_ascii": False})


@login_required
def export_audit_file_markdown(request, pk: int):
    """
    单文件报告 Markdown 导出 API。

    URL:
        GET /indicator_audit/file/<pk>/export/markdown/

    功能：
        - 将指定 AuditFile 的审核结果渲染为 Markdown 文本并作为附件下载。
        - 不在数据库中额外存储导出结果。
    """

    audit_file = get_object_or_404(AuditFile, pk=pk, created_by=request.user)
    if not audit_file.report_json:
        raise Http404("该文件尚未生成审核报告。")
    content = build_file_report_markdown(audit_file)
    filename = f"audit-report-{audit_file.id}.md"
    response = HttpResponse(
        content,
        content_type="text/markdown; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_audit_file_pdf(request, pk: int):
    """
    单文件报告 PDF 导出 API。

    URL:
        GET /indicator_audit/file/<pk>/export/pdf/

    功能：
        - 将指定 AuditFile 的审核结果渲染为 PDF 字节流并作为附件下载。
        - 使用内存生成，不在磁盘落地中间文件。
    """

    audit_file = get_object_or_404(AuditFile, pk=pk, created_by=request.user)
    if not audit_file.report_json:
        raise Http404("该文件尚未生成审核报告。")
    pdf_bytes = build_file_report_pdf(audit_file)
    filename = f"audit-report-{audit_file.id}.pdf"
    response = HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
