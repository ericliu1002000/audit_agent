from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class BudgetAuditPage(LoginRequiredMixin, TemplateView):
    """
    预算审核（单条）页面。

    URL:
        /budget_audit/audit/
    """

    template_name = "budget_audit/budget_audit_page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = "budget_audit"
        return context

