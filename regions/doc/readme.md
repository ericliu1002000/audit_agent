# Regions API

## 获取全部省份
- **Method**: `GET`
- **URL**: `/regions/api/provinces/`
- **Response**: `results` 数组内每个对象包含 `id`, `name`, `code`。

示例：

```bash
curl -X GET http://localhost:8000/regions/api/provinces/
```

```json
{
  "results": [
    {"id": 1, "name": "北京市", "code": "11"},
    {"id": 2, "name": "天津市", "code": "12"}
  ]
}
```

## 根据省份获取城市
- **Method**: `GET`
- **URL**: `/regions/api/provinces/<province_id>/cities/`
- **Path 参数**:
  - `province_id`：省份主键 ID。
- **Response**: `province` 字段返回省份基础信息；`results` 数组返回该省份下全部城市，每项包含 `id`, `name`, `code`。若 `province_id` 不存在，返回 404。

示例：

```bash
curl -X GET http://localhost:8000/regions/api/provinces/1/cities/
```

```json
{
  "province": {"id": 1, "name": "北京市", "code": "11"},
  "results": [
    {"id": 1, "name": "北京市", "code": "1101"}
  ]
}
```
