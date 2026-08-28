# 物品图片批量下载工具

输入物品清单和每个物品要几张图,自动到 DuckDuckGo 搜图并下载到本地,按物品分文件夹，并生成一个 `summary.html` 汇总页面。

## 安装（只需一次）

```bash
pip install ddgs requests pillow
```

## 用法

### 方式 1：用清单文件

编辑 `items.txt`，每行一个物品：

```
excavator demolition | 5
concrete crusher attachment | 4
safety helmet construction, 6
hydraulic breaker
```

- 分隔符 `|`、`,`、`=` 都可以
- 不写数量就用默认值（`--count`，默认 5）
- `#` 开头的行忽略

然后运行：

```bash
python fetch_images.py
```

### 方式 2：命令行直接写

```bash
python fetch_images.py "挖掘机=3" "safety helmet=10" "破碎锤"
```

## 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--items 文件` | 清单文件路径 | `items.txt` |
| `--out 目录` | 下载目录 | `downloads` |
| `--count N` | 没写数量时每个物品下载几张 | `5` |
| `--min-size N` | 图片最短边像素下限，过滤小图/图标 | `300` |
| `--timeout N` | 单张图片下载超时（秒） | `20` |
| `--safesearch on/moderate/off` | 安全搜索 | `moderate` |

## 输出

```
downloads/
  excavator demolition/
    001.jpg  002.jpg  ...
  safety helmet construction/
    001.jpg  ...
  summary.html      <- 用浏览器打开看所有图 + 每个物品的需求数量
```

## 说明

- 图片来自 DuckDuckGo 公开图片搜索，可能有版权，仅供内部参考/识别用途。
- 中文物品名可用，但英文关键词通常搜到的图更多更准。
- 每个物品会自动多搜一些候选，下载失败或重复的会跳过，直到凑够数量。
