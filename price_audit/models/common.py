"""价格审核模型公共工具。"""


def government_price_source_upload_to(instance, filename):
    """生成政府标准价源文件上传路径。

    功能说明:
        按“年份/地区/原始文件名”的层级组织上传文件，便于后台追溯来源文件。
    使用示例:
        path = government_price_source_upload_to(batch, "prices.xlsx")
    输入参数:
        instance: `GovernmentPriceBatch` 实例。
        filename: 原始上传文件名。
    输出参数:
        str: 形如 `price_audit/government_prices/2026/天津/prices.xlsx` 的相对路径。
    """

    year = instance.year or "unknown"
    region = (instance.region_name or "unknown").strip().replace("/", "_")
    return f"price_audit/government_prices/{year}/{region}/{filename}"
