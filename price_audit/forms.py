"""价格审核后台表单。"""

from django import forms


class GovernmentPriceImportForm(forms.Form):
    """后台导入政府标准价 Excel 的表单。"""

    excel_file = forms.FileField(
        label="Excel 文件",
        help_text="请上传 .xlsx 格式文件。",
    )
    region_name = forms.CharField(
        label="地区",
        max_length=100,
        help_text="例如：天津。",
    )
    year = forms.IntegerField(
        label="年份",
        min_value=2000,
        max_value=2100,
    )
    default_tax_included = forms.BooleanField(
        label="默认按含税处理",
        required=False,
        initial=True,
        help_text="如果表格没有“是否含税”列，或单元格为空，则按含税处理。",
    )
    remark = forms.CharField(
        label="备注",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_excel_file(self):
        """
        功能说明:
            校验后台上传文件格式，避免用户误传非 Excel 文件。
        输入参数:
            无。
        输出参数:
            UploadedFile: 通过校验后的上传文件对象。
        """

        excel_file = self.cleaned_data["excel_file"]
        filename = (excel_file.name or "").lower()
        if not filename.endswith(".xlsx"):
            raise forms.ValidationError("仅支持上传 .xlsx 格式文件。")
        return excel_file
