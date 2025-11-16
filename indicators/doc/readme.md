# Indicators API

## 资金用途推荐
- **Method**: `GET`
- **URL**: `/indicators/api/fund-usage/recommendations/`
- **Query 参数**:
  - `query`：必填，用户输入的自然语言问题或需求。
  - `province_id`：选填，数值型，限定推荐结果关联的省份。
- **Response**:
  - 成功时返回 `results` 数组，每个元素为一条推荐建议。
  - 当 `query` 为空时返回 `400`，当参数无法解析或内部错误时会返回相应的错误信息。

示例：

```bash
curl -G \
  --data-urlencode "query=2023年教育支出怎么合规" \
  --data-urlencode "province_id=11" \
  http://localhost:8000/indicators/api/fund-usage/recommendations/
```

```json
{
  "results": [
    "建议一：增加对义务教育薄弱环节改造投入……",
    "建议二：重点推进职业教育提质工程……"
  ]
}
```

错误示例（query 为空）：

```json
{
  "error": "query 参数不能为空"
}
```
