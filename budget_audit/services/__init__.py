def import_standard_price_excel(*args, **kwargs):
    from budget_audit.services.standard_sync import import_standard_price_excel as _impl

    return _impl(*args, **kwargs)


def match_vendor_quote_excel(*args, **kwargs):
    from budget_audit.services.match_service import match_vendor_quote_excel as _impl

    return _impl(*args, **kwargs)


__all__ = ["import_standard_price_excel", "match_vendor_quote_excel"]
